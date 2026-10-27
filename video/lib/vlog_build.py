#!/usr/bin/env python3
"""
vlog_build.py - the REUSABLE documentary-vlog render engine (youtube-vlog agent).

One frame-exact engine, one EDL, three staged deliverables (the vlog build & render policy):

  stage "fcpxml"  ->  a Final Cut Pro project (.fcpxml) of the cut, referencing the RAW clips,
                      NO grade / NO grain. Open it in Final Cut and scrub the edit. This is the
                      FIRST thing to produce and get approved.  (the creator may then export the finished
                      video themselves from Final Cut - in which case stages 540/4k are not needed.)
  stage "540"     ->  a 960x540 mp4 WITH the grade + grain, fast encode. The look-proof.
  stage "720"     ->  a 1280x720 mp4 WITH the grade + grain (optional middle rung).
  stage "4k"      ->  a 3840x2160 mp4 WITH the grade + grain, quality encode. The final render.

A per-episode script just defines its config + BEATS (the EDL) and calls run(stage). It owns NO
render logic. See the youtube-vlog
agent (section 10 / the build & render policy) for how this is meant to be used.

EDL model (BEATS = ordered list):
  music beat:  dict(kind="music", music=<key>, mvol=0.85, fadein=0.02, shots=[(clip,tin,len), ...])
  voice beat:  dict(kind="voice", voice=(clip,cin,cout), anchor=0, shots=[(clip,tin,len_or_None)],
                    fadeout=0.12)                          # voice beats NEVER get music
  - clip is a RAW-relative path like "sony/C1214.MP4" / "gopro/GX010260.MP4" / "screen-rec/scr1.mp4".
  - music <key> resolves to <music_dir>/<key>.mp3.
  - In a voice beat the first `anchor` shots play BEFORE the voice audio anchor; the rest fill the
    remaining voice frames (last/None-length shot soaks up whatever is left). A shot whose clip !=
    the voice clip is a B-roll-over-voice overlay (relevant screen/keyboard/product surface).
"""
import os, sys, json, hashlib, math, subprocess, urllib.parse
import xml.sax.saxutils as X
import xml.dom.minidom as MD

# stage -> render settings. All render stages bake grade + grain; fcpxml bakes neither.
STAGES = {
    "540": dict(w=960,  h=540,  crf="24", preset="veryfast", label="540p"),
    "720": dict(w=1280, h=720,  crf="20", preset="veryfast", label="720p"),
    "4k":  dict(w=3840, h=2160, crf="18", preset="medium",   label="4K"),
}

# default grade (the sandy exposure+grain recipe that shipped; per-clip luma curves + film grain).
DEFAULT_GRADE = dict(
    std="0/0.07 0.2/0.22 1/1",                        # normal/dark clips: tiny toe lift
    bright="0/0.08 0.25/0.26 0.65/0.585 1/0.91",      # blown clips: toe lift + highlight tame
    grain="noise=alls=4:allf=t+u",                    # monochromatic film grain
)


class VlogBuild:
    def __init__(self, *, base, raw, music_dir, out_dir, out_basename,
                 event_name="Vlog", project_name="Rough cut (from Claude)",
                 fps=25, bright_clips=None, grade=None):
        self.base = base
        self.raw = raw
        self.music_dir = music_dir
        self.out_dir = out_dir
        self.out_basename = out_basename
        self.event_name = event_name
        self.project_name = project_name
        self.fps = fps
        self.bright_clips = set(bright_clips or [])
        self.grade = dict(DEFAULT_GRADE, **(grade or {}))
        self.beats = []
        self._dur = {}
        os.makedirs(out_dir, exist_ok=True)

    # ---- helpers ----
    def path_of(self, clip):
        return clip if os.path.isabs(clip) else f"{self.raw}/{clip}"

    def cid(self, clip):
        return os.path.splitext(os.path.basename(clip))[0].replace(" ", "_")

    def fr(self, sec):
        return int(round(sec * self.fps))

    def _curve(self, clip):
        return self.grade["bright"] if self.cid(clip) in self.bright_clips else self.grade["std"]

    def _geom(self, clip, w, h):
        # gopro/screen-rec/screenrec differ in aspect -> fill by scale+crop; sony -> plain scale
        if "gopro" in clip or "screen-rec" in clip or "screenrec" in clip:
            return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        return f"scale={w}:{h}:flags=lanczos"

    def clipdur(self, clip):
        if clip not in self._dur:
            r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                                "-of","default=nk=1:nw=1", self.path_of(clip)],
                               capture_output=True, text=True).stdout.strip()
            self._dur[clip] = float(r or "0")
        return self._dur[clip]

    # ---- shared render expansion (frame-exact): BEATS -> shots + audio events ----
    def _expand(self):
        shots, audio, gf = [], [], 0
        for be in self.beats:
            bs = gf
            if be["kind"] == "voice":
                clip, cin, cout = be["voice"]; anchor = be.get("anchor", 0)
                vframes = self.fr(cout - cin); sf = []
                for c, tin, ln in be["shots"][:anchor]:
                    sf.append((c, tin, self.fr(ln)))
                acc = 0; post = be["shots"][anchor:]
                for i, (c, tin, ln) in enumerate(post):
                    n = (vframes - acc) if (ln is None or i == len(post) - 1) else self.fr(ln)
                    sf.append((c, tin, n)); acc += n
                anchor_gf = bs + sum(n for _, _, n in sf[:anchor])
                for c, tin, n in sf:
                    shots.append((c, tin, n)); gf += n
                audio.append(dict(k="voice", clip=clip, cin=cin, dur=vframes / self.fps,
                                  start=anchor_gf / self.fps, vol=1.25, fadeout=be.get("fadeout", 0.12)))
            else:
                for c, tin, ln in be["shots"]:
                    shots.append((c, tin, self.fr(ln))); gf += self.fr(ln)
                audio.append(dict(k="music", file=f"{self.music_dir}/{be['music']}.mp3",
                                  dur=(gf - bs) / self.fps, start=bs / self.fps,
                                  vol=be["mvol"], fadein=be.get("fadein", 0.02)))
        return shots, audio, gf

    def preflight(self, shots):
        bad = [(c, tin, n) for c, tin, n in shots
               if tin + n / self.fps > self.clipdur(c) - 0.05]
        if bad:
            for c, tin, n in bad:
                print(f"OVERRUN: {c} tin={tin} len={n/self.fps:.2f} but clip is {self.clipdur(c):.2f}s")
            sys.exit("Fix the EDL: shots run past their source.")

    # ---- RENDER stage (grade + grain baked) ----
    def render(self, stage):
        st = STAGES[stage]; W, H = st["w"], st["h"]
        shots, audio, total_f = self._expand()
        self.preflight(shots)
        TOTAL = total_f / self.fps
        viddir = f"{self.out_dir}/vid-{stage}"; os.makedirs(viddir, exist_ok=True)
        out = f"{self.out_dir}/{self.out_basename}-{stage}.mp4"

        concat = []
        for idx, (clip, tin, n) in enumerate(shots):
            vf = f"{self._geom(clip,W,H)},curves=master='{self._curve(clip)}',{self.grade['grain']},fps={self.fps},format=yuv420p"
            source_id = hashlib.sha256(os.path.realpath(self.path_of(clip)).encode()).hexdigest()[:8]
            grade_id = hashlib.sha256(json.dumps({
                "grade": self.grade,
                "curve": self._curve(clip),
            }, sort_keys=True).encode()).hexdigest()[:8]
            in_us = int(round(tin * 1_000_000))
            seg = (f"{viddir}/{idx:03d}_{self.cid(clip)}_{source_id}_"
                   f"in{in_us}us_{n}f_g{grade_id}.mp4")
            concat.append(seg)
            if os.path.exists(seg) and os.path.getsize(seg) > 4000:
                continue
            subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(tin),"-i",self.path_of(clip),
                            "-vf",vf,"-frames:v",str(n),"-r",str(self.fps),"-an",
                            "-c:v","libx264","-crf",st["crf"],"-preset",st["preset"],
                            "-pix_fmt","yuv420p","-video_track_timescale","12800",seg], check=True)

        catfile = f"{self.out_dir}/concat-{stage}.txt"
        with open(catfile, "w") as f:
            for c in concat:
                f.write(f"file '{c}'\n")
        vidmp4 = f"{viddir}.mp4"
        subprocess.run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0",
                        "-i",catfile,"-c","copy",vidmp4], check=True)
        vd = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                                   "-of","default=nk=1:nw=1",vidmp4],
                                  capture_output=True,text=True).stdout.strip())
        print(f"[{st['label']}] video {vd:.3f}s computed {TOTAL:.3f}s "
              f"drift {abs(vd-TOTAL)*1000:.0f}ms ({len(shots)} shots)")

        # audio mix: voice dry (no music), music only under montage beats
        inputs, parts, labels = [], [], []
        for ev in audio:
            inputs += ["-i", (self.path_of(ev["clip"]) if ev["k"] == "voice" else ev["file"])]
        for i, ev in enumerate(audio):
            ms = int(round(ev["start"] * 1000)); lab = f"a{i}"
            if ev["k"] == "voice":
                fd = ev.get("fadeout", 0.12); d = ev["dur"]; fo = max(0.05, d - fd)
                parts.append(f"[{i}:a]atrim={ev['cin']}:{ev['cin']+d:.3f},asetpts=PTS-STARTPTS,"
                             f"afade=t=in:st=0:d=0.06,afade=t=out:st={fo:.3f}:d={fd},volume={ev['vol']},"
                             f"aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[{lab}]")
            else:
                d = ev["dur"]; fo = max(0.1, d - 1.0)
                parts.append(f"[{i}:a]atrim=0:{d:.3f},asetpts=PTS-STARTPTS,"
                             f"afade=t=in:st=0:d={ev.get('fadein',0.02)},afade=t=out:st={fo:.3f}:d=1.0,"
                             f"volume={ev['vol']},aformat=sample_rates=48000:channel_layouts=stereo,"
                             f"adelay={ms}|{ms}[{lab}]")
            labels.append(f"[{lab}]")
        fc = (
            ";".join(parts) + ";" + "".join(labels)
            + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
            + "alimiter=limit=0.80:level=false,apad[mix]"
        )
        audiowav = f"{self.out_dir}/audio-{stage}.wav"
        subprocess.run(["ffmpeg","-y","-loglevel","error"]+inputs+["-filter_complex",fc,"-map","[mix]",
                        "-t",str(TOTAL),"-c:a","pcm_s16le",audiowav], check=True)
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",vidmp4,"-i",audiowav,
                        "-map","0:v:0","-map","1:a:0","-t",str(TOTAL),"-c:v","copy","-c:a","aac",
                        "-b:a","256k","-dn","-map_metadata","-1","-movflags","+faststart",out], check=True)
        print(f"FINAL -> {out}\nTOTAL {TOTAL:.1f}s = {TOTAL/60:.2f} min")
        return out

    # ---- FCPXML stage (no grade / no grain; raw clips on a 25fps 4K timeline) ----
    def _probe(self, abspath, _cache={}):
        if abspath in _cache:
            return _cache[abspath]
        def pf(*a):
            return subprocess.run(["ffprobe","-v","error",*a,abspath],
                                  capture_output=True,text=True).stdout.strip()
        dur = float(pf("-show_entries","format=duration","-of","default=nk=1:nw=1") or "0")
        vs = pf("-select_streams","v:0","-show_entries","stream=width,height,r_frame_rate",
                "-of","default=nk=1:nw=1").splitlines()
        has_v = len(vs) >= 2
        w = int(vs[0]) if has_v else 0; h = int(vs[1]) if has_v else 0
        rate = vs[2] if len(vs) > 2 else "25/1"
        a = pf("-select_streams","a:0","-show_entries","stream=index","-of","default=nk=1:nw=1")
        n, d = (rate.split("/") + ["1"])[:2]; n, d = int(n), int(d)
        _cache[abspath] = dict(w=w,h=h,fdn=d,fdd=n,dur=dur,hasA=bool(a),hasV=has_v,
                               name=os.path.splitext(os.path.basename(abspath))[0])
        return _cache[abspath]

    def fcpxml(self):
        FPS = self.fps
        shots, _, _ = self._expand()
        self.preflight(shots)

        def rat(sec):
            return f"{int(round(sec*FPS))}/{FPS}s"
        def ratsrc(m, sec):
            fps_n, fps_d = m["fdd"], m["fdn"]
            frames = int(round(sec * fps_n / fps_d))
            return f"{frames*fps_d}/{fps_n}s" if fps_n != 1 else f"{frames}/{fps_n}s"

        # walk BEATS -> primary storyline (voice clips + montage shots) + connected (overlays + music)
        prim, conn, gf = [], [], 0
        for be in self.beats:
            bs = gf
            if be["kind"] == "voice":
                clip, cin, cout = be["voice"]; anchor = be.get("anchor", 0)
                vframes = self.fr(cout - cin); sf = []
                for c, tin, ln in be["shots"][:anchor]:
                    sf.append((c, tin, self.fr(ln)))
                acc = 0; post = be["shots"][anchor:]
                for i, (c, tin, ln) in enumerate(post):
                    n = (vframes - acc) if (ln is None or i == len(post) - 1) else self.fr(ln)
                    sf.append((c, tin, n)); acc += n
                prim.append(dict(clip=clip, cin=cin, dur=vframes, offset=bs, mute=False))
                o = bs
                for c, tin, n in sf:
                    if c != clip:
                        conn.append(dict(clip=c, cin=tin, dur=n, offset=o, kind="video"))
                    o += n
                gf += vframes
            else:
                for c, tin, ln in be["shots"]:
                    n = self.fr(ln)
                    prim.append(dict(clip=c, cin=tin, dur=n, offset=gf, mute=True))
                    gf += n
                conn.append(dict(clip=f"{self.music_dir}/{be['music']}.mp3",
                                 cin=0.0, dur=gf - bs, offset=bs, kind="audio",
                                 vol=be.get("mvol", 1.0)))
        TOTAL = gf

        fmts, fmt_ids, assets, asset_ids = {}, {}, {}, {}
        def fmt_id(m):
            key = (m["w"], m["h"], m["fdn"], m["fdd"])
            if key not in fmt_ids:
                fid = f"f{len(fmt_ids)+1}"; fmt_ids[key] = fid
                if m["w"]:
                    fmts[fid] = (f'<format id="{fid}" frameDuration="{m["fdn"]}/{m["fdd"]}s" '
                                 f'width="{m["w"]}" height="{m["h"]}" colorSpace="1-1-1 (Rec. 709)"/>')
                else:
                    fmts[fid] = f'<format id="{fid}" frameDuration="{m["fdn"]}/{m["fdd"]}s"/>'
            return fmt_ids[key]
        def asset_id(abspath):
            if abspath in asset_ids:
                return asset_ids[abspath]
            m = self._probe(abspath); aid = f"a{len(asset_ids)+1}"; asset_ids[abspath] = aid
            url = "file://" + urllib.parse.quote(abspath)
            assets[aid] = (f'<asset id="{aid}" name="{X.escape(m["name"])}" start="0s" '
                           f'duration="{rat(m["dur"])}" hasVideo="{1 if m["hasV"] else 0}" '
                           f'hasAudio="{1 if m["hasA"] else 0}" format="{fmt_id(m)}" '
                           f'audioSources="1" audioChannels="2">'
                           f'<media-rep kind="original-media" src="{url}"/></asset>')
            return aid

        for it in prim: asset_id(self.path_of(it["clip"]))
        for it in conn: asset_id(self.path_of(it["clip"]))

        SEQFMT = ('<format id="fSEQ" frameDuration="1/25s" width="3840" height="2160" '
                  'colorSpace="1-1-1 (Rec. 709)"/>')
        spine_parts = []
        for p in sorted(prim, key=lambda x: x["offset"]):
            ap = self.path_of(p["clip"]); aid = asset_id(ap); m = self._probe(ap)
            off = rat(p["offset"]/FPS); dur = rat(p["dur"]/FPS); start = ratsrc(m, p["cin"])
            # Rendered montage shots and connected B-roll are video-only. Keep the
            # raw source audio muted in Final Cut too, so private call audio cannot
            # leak underneath music or the dry piece-to-camera track.
            children = '<adjust-volume amount="-96dB"/>' if p.get("mute") else ""
            p0, p1 = p["offset"], p["offset"] + p["dur"]
            # FCPXML LAW (learned the hard way on the first montage): an anchored
            # item's offset is in the PARENT'S source-time coordinates, not sequence time.
            # To place a connected clip at timeline frame T under a parent with source-in
            # `cin` (seconds) at timeline frame p0:  offset_seconds = cin + (T - p0)/FPS.
            # Using raw timeline offsets shifts music/overlays by (cin - p0/FPS) per parent
            # on import and destroys beat sync in Final Cut.
            def anch(tl_frames):
                return rat(p["cin"] + (tl_frames - p0) / FPS)
            for c in conn:
                if c["kind"] == "audio":
                    c0, c1 = c["offset"], c["offset"] + c["dur"]
                    overlap0, overlap1 = max(p0, c0), min(p1, c1)
                    if overlap0 >= overlap1:
                        continue
                    cap = self.path_of(c["clip"]); caid = asset_id(cap); cm = self._probe(cap)
                    coff = anch(overlap0); cdur = rat((overlap1-overlap0)/FPS)
                    cstart = ratsrc(cm, c["cin"] + (overlap0-c0)/FPS)
                    amount = 20 * math.log10(max(c.get("vol", 1.0), 1e-6))
                    children += (f'<audio ref="{caid}" lane="-1" offset="{coff}" duration="{cdur}" '
                                 f'start="{cstart}" name="{X.escape(cm["name"])}">'
                                 f'<adjust-volume amount="{amount:.2f}dB"/></audio>')
                elif p0 <= c["offset"] < p1:
                    cap = self.path_of(c["clip"]); caid = asset_id(cap); cm = self._probe(cap)
                    coff = anch(c["offset"])
                    cdur = rat(min(c["dur"], p1 - c["offset"])/FPS); cstart = ratsrc(cm, c["cin"])
                    children += (f'<asset-clip ref="{caid}" lane="1" offset="{coff}" duration="{cdur}" '
                                 f'start="{cstart}" name="{X.escape(cm["name"])}" format="{fmt_id(cm)}">'
                                 f'<adjust-volume amount="-96dB"/></asset-clip>')
            spine_parts.append(f'<asset-clip ref="{aid}" offset="{off}" duration="{dur}" start="{start}" '
                               f'name="{X.escape(m["name"])}" format="{fmt_id(m)}">{children}</asset-clip>')

        doc = (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n'
               f'<fcpxml version="1.9">\n  <resources>\n    {SEQFMT}\n'
               f'    {"".join(fmts.values())}\n    {"".join(assets.values())}\n  </resources>\n'
               f'  <library>\n    <event name="{X.escape(self.event_name)}">\n'
               f'      <project name="{X.escape(self.project_name)}">\n'
               f'        <sequence format="fSEQ" tcStart="0s" tcFormat="NDF" duration="{rat(TOTAL/FPS)}">\n'
               f'          <spine>\n            {"".join(spine_parts)}\n          </spine>\n'
               f'        </sequence>\n      </project>\n    </event>\n  </library>\n</fcpxml>\n')
        MD.parseString(doc)  # validate well-formedness
        out = f"{self.out_dir}/{self.out_basename}.fcpxml"
        open(out, "w").write(doc)
        print(f"OK  {len(prim)} primary clips, {len(conn)} connected (music+overlays), {len(assets)} assets")
        print(f"timeline {TOTAL/FPS:.1f}s -> {out}")
        return out

    # ---- dispatcher ----
    def run(self, stage):
        stage = (stage or "fcpxml").lower()
        if stage == "fcpxml":
            return self.fcpxml()
        if stage == "all":
            self.fcpxml(); self.render("540"); return self.render("4k")
        if stage in STAGES:
            return self.render(stage)
        sys.exit(f"unknown stage '{stage}'. use: fcpxml | 540 | 720 | 4k | all")
