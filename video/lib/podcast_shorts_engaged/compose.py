"""Stage 2: compositors.

ENGAGEMENT (the headline format): a concat of exact-frame pieces on the approved timeline, one per state:
  F  full frame  = base_full (speaker, or the listener's reaction cutaway), optional punch-in (punch_z about the mouth
                   row for the tracked camera, about the centre line for the static one)
  S  split       = TOP panel (the Remotion top-panel animation track, or a literal real clip) over the BOTTOM panel
                   (base_panel: whoever the approved edit shows), 6 px seam at y 1917
then the engagement captions (fixed row), then the hook card for the whole short; audio = audio_final.wav untouched.
CLEAN (the companion): base_full + clean captions + hook + the same audio.
plan_*() only builds strings; nothing renders without the caller choosing to (the creator's explicit export approval).
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kitconfig  # noqa: E402
from . import timeline as TL

SEAM = "drawbox=x=0:y=1917:w=2160:h=6:color=0x" + kitconfig.palette()["background"].lstrip("#") + "@1:t=fill"     # background-colour hairline on the seam
ENC = ["-c:v", "libx264", "-preset", "slow", "-crf", "20", "-maxrate", "32M", "-bufsize", "64M", "-profile:v", "high", "-level", "5.1",
       "-pix_fmt", "yuv420p", "-r", "25", "-fps_mode", "cfr", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]


def punch_crop(z, pivot_y, W=2160, H=3840):
    w = int(W / z) // 2 * 2; h = int(H / z) // 2 * 2
    x = int(round(W / 2 - W / 2 / z)); y = int(round(pivot_y - pivot_y / z))
    return w, h, x, y


def punch_z_allowed(z, hair_row, pivot_y, hook_clear):
    """largest punch-in <= z that keeps the hair >= hook_clear; below 1.03 the punch-in is dropped (1.0)"""
    zmax = (pivot_y - hook_clear) / (pivot_y - hair_row) if pivot_y > hair_row else z
    zz = min(z, zmax)
    return 1.0 if zz < 1.03 else round(zz, 3)


def punch_pivot_up(z, hair_row, pivot_y, hc, p_min=300):
    """Standard section 6): keep the full punch-in (a visible change) and move its
    pivot UP to the highest row that still keeps the hair >= hc (punched hair = p - (p - hair) * z >= hc <=>
    p <= (hair * z - hc) / (z - 1)); only if that row would be above p_min, reduce z instead. Returns (z, pivot)."""
    p_max = (hair_row * z - hc) / (z - 1)
    if p_max >= p_min: return z, min(pivot_y, p_max)
    return punch_z_allowed(z, hair_row, pivot_y, hc), pivot_y


def resolve_punch(ep, z, who, fr_, hook_bottom):
    """the punch-in actually applied for one full-frame piece -> (z, pivot, info); info keys in the reference-build order"""
    pivot = fr_["mouth_y"] if ep.cam_kind(who) == "tracked" else ep.H / 2
    if hook_bottom is not None and "hair_y_min" in fr_:      # hair >= hook + 20 px inside the punch-in
        clear = max(ep.c.get("hook_clear_y", 570), hook_bottom + ep.c.get("hook_punch_margin", 20))
        z_req = z
        if ep.c.get("punch_pivot_up", True):   # reference-build + standard: hair >= hook bottom + margin + 1
            z, pivot = punch_pivot_up(z, fr_["hair_y_min"], pivot, hook_bottom + ep.c.get("hook_punch_margin", 20) + 1)
        else: z = punch_z_allowed(z, fr_["hair_y_min"], pivot, clear)
        return z, pivot, {"z_requested": z_req, "z": z, "pivot_y": round(pivot), "speaker": who,
                          "hair_clearance_punch": round(pivot - (pivot - fr_["hair_y_min"]) * z - hook_bottom, 1)}
    return z, pivot, {"z": z, "pivot_y": round(pivot), "speaker": who}


def src_info(path):
    js = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "json", path],
                                   capture_output=True, text=True).stdout)["streams"][0]
    return js["width"], js["height"]


def broll_chain(sp, path, n, W, H, idx):
    """one literal real clip -> exactly n frames of WxH 25p with a slow 7% pan (never static)."""
    sw, sh = src_info(path)
    ar = W / H; z = sp.get("zoom", 1.0)
    if sw / sh > ar: ch = sh / z; cw = ch * ar
    else: cw = sw / z; ch = cw / ar
    cw, ch = int(cw) // 2 * 2, int(ch) // 2 * 2
    cx = sp.get("cx", 0.5) * sw; cy = sp.get("cy", 0.5) * sh
    x = int(min(max(cx - cw / 2, 0), sw - cw)); y = int(min(max(cy - ch / 2, 0), sh - ch))
    spd = sp.get("speed", 1.0)
    PW, PH = int(W * 1.07) // 2 * 2, int(H * 1.07) // 2 * 2
    mx, my = PW - W, PH - H
    d = max(n - 1, 1); dirn = 1 if idx % 2 == 0 else -1
    xe = f"{mx / 2:.1f}+{dirn * mx / 2:.1f}*(2*n/{d}-1)"; ye = f"{my / 2:.1f}"
    sharpen = ",unsharp=5:5:0.6:5:5:0.0" if sw < 1900 else ""
    return (f"setpts=(PTS-STARTPTS)/{spd},fps=25:round=near,settb=1/25,setpts=N,trim=end_frame={n},"
            f"crop={cw}:{ch}:{x}:{y},scale={PW}:{PH}:flags=lanczos{sharpen},crop={W}:{H}:'{xe}':'{ye}',setsar=1,format=yuv420p")


def plan_engagement(ep, slug, caps_path, base_full_rec, preview_dir=None, hook_bottom=None, review_out=None):
    """review_out (remote-build,: a low-res REVIEW file (720x1280, 25p, H.264 CRF 23, SAR 1:1) at that path, same
    graph as the 4K engagement render apart from the final scale (needs the creator's export go-ahead like any video)."""
    S = ep.short(slug); E = S["engagement"]; fps = ep.fps
    pcs, TF = TL.state_pieces(E["states"], E["T"], fps); T = TF / fps
    d = ep.altdir(slug)
    full = os.path.join(d, "base_full.mp4"); panel = os.path.join(d, "base_panel.mp4"); anim = os.path.join(d, "top_anim.mp4")
    title = os.path.join(ep.edir(slug), "title_4k.png"); aud = os.path.join(ep.edir(slug), "audio_final.wav")
    inputs = [["-i", full], ["-i", panel], ["-i", anim], ["-loop", "1", "-t", f"{T + 0.5:.2f}", "-framerate", "25", "-i", title], ["-i", aud]]
    nF = sum(1 for p in pcs if p[2] == "F"); nS = sum(1 for p in pcs if p[2] == "S")
    nA = sum(1 for p in pcs if p[2] == "S" and p[3]["top"] == "anim")
    fc = [f"[0:v]settb=1/25,setpts=N,split={max(nF, 1)}" + "".join(f"[f{i}]" for i in range(max(nF, 1))),
          f"[1:v]settb=1/25,setpts=N,split={max(nS, 1)}" + "".join(f"[p{i}]" for i in range(max(nS, 1))),
          f"[2:v]settb=1/25,setpts=N,split={max(nA, 1)}" + "".join(f"[an{i}]" for i in range(max(nA, 1)))]
    if nF == 0: fc.append("[f0]nullsink")
    if nS == 0: fc.append("[p0]nullsink")
    if nA == 0: fc.append("[an0]nullsink")
    m, _ = ep.seg_map(slug)
    shots, framing = base_full_rec["shots"], base_full_rec["framing"]
    tracked = ep.short(slug).get("owner_camera", ep.c.get("host_camera", "A"))
    cf = cs = ca = 0; cat = []; log = []; bidx = 0
    for j, (a, b, k, sp0) in enumerate(pcs):
        sp = dict(sp0); n = b - a; lab = f"pc{j}"
        if k == "F":
            z = ep.c["punch_z"] if sp.get("z", 1.0) != 1.0 else 1.0
            who = next((sh["shot"] for sh in shots if sh["out_start"] * 25 <= a < sh["out_end"] * 25), tracked)
            if z != 1.0:
                si = next(i for i, (a0_, a1_, n_, t0_) in enumerate(m) if int(round(t0_ * 25)) <= a < int(round(t0_ * 25)) + n_)
                fr_ = next(x for x in framing if x["seg"] == si and x["speaker"] == who)
                z, pivot, info = resolve_punch(ep, z, who, fr_, hook_bottom); sp.update(info)
            if z != 1.0:
                cw, chh, cx, cy = punch_crop(z, pivot)
            zf = "" if z == 1.0 else f",crop={cw}:{chh}:{cx}:{cy},scale=2160:3840:flags=lanczos,setsar=1"
            fc.append(f"[f{cf}]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS{zf}[{lab}]"); cf += 1
        elif k == "S":
            fc.append(f"[p{cs}]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[bot{j}]"); cs += 1
            if sp["top"] == "anim":
                fc.append(f"[an{ca}]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[top{j}]"); ca += 1
            else:
                ii = len(inputs); spd = sp.get("speed", 1.0); path = ep.p(ep.c["broll"][sp["top"]])
                inputs.append(["-ss", f"{sp['in']:.3f}", "-t", f"{n / 25 * spd + 1.0:.3f}", "-i", path])
                fc.append(f"[{ii}:v]{broll_chain(sp, path, n, 2160, 1920, bidx)}[top{j}]"); bidx += 1
            fc.append(f"[top{j}][bot{j}]vstack=shortest=1,{SEAM}[{lab}]")
        else:  # X: a literal real clip full frame
            ii = len(inputs); spd = sp.get("speed", 1.0); path = ep.p(ep.c["broll"][sp["top"]])
            inputs.append(["-ss", f"{sp['in']:.3f}", "-t", f"{n / 25 * spd + 1.0:.3f}", "-i", path])
            fc.append(f"[{ii}:v]{broll_chain(sp, path, n, 2160, 3840, bidx)}[{lab}]"); bidx += 1
        cat.append(lab)
        log.append({"t0": round(a / 25, 2), "t1": round(b / 25, 2), "kind": k, **{kk: v for kk, v in sp.items()}})
    fc.append("".join(f"[{c}]" for c in cat) + f"concat=n={len(cat)}:v=1:a=0,settb=1/25[cat]")
    fc.append(f"[cat]ass={caps_path}[cap]")
    fc.append("[3:v]format=rgba,settb=1/25,setpts=N[ttl]")
    fc.append("[cap][ttl]overlay=0:0:shortest=1" + (",scale=720:1280:flags=lanczos,setsar=1" if review_out else ",scale=1080:1920:flags=lanczos" if preview_dir else "")
              + ",format=yuv420p[vout]")
    fpath = os.path.join(d, "filter_alt_review.txt" if review_out else "filter_alt.txt" if not preview_dir else "filter_alt_preview.txt")
    out = review_out or (os.path.join(ep.final_dir(slug), f"{slug}-ALT-engagement.mp4") if not preview_dir else os.path.join(preview_dir, f"{slug}-preview.mp4"))
    enc = ENC if not (preview_dir or review_out) else [("veryfast" if x == "slow" else ("23" if review_out else "16") if x == "20" else
                                                       "6M" if (review_out and x == "32M") else "12M" if (review_out and x == "64M") else x) for x in ENC]
    cmd = ["ffmpeg", "-v", "error", "-y"] + [x for i in inputs for x in i] + [
        "-filter_complex_script", fpath, "-map", "[vout]", "-map", "4:a"] + enc + ["-t", f"{T:.3f}", "-movflags", "+faststart", out]
    changes, gaps, mx = TL.change_log(pcs, shots, E["steps"], T, fps, eff_z=[p.get("z", 1.0) if p["kind"] == "F" else None for p in log])
    edl = {"slug": slug, "duration": T, "pieces": log, "changes": changes, "max_gap": mx}
    return fc, cmd, edl, fpath


def plan_clean(ep, slug, caps_path, T, base_full_rec=None, hook_bottom=None):
    """clean = base_full + clean captions + hook + audio. Optional short key "clean_punch" [[t0, t1, z], ...] (output s):
    punch-ins about the speaker's mouth row with the same hook rule as the engagement version (multicam-build: the approved v3 cut
    alternated 1.0 / 1.1 pieces to hide its jump cuts; carried over at the house 1.08)."""
    d = ep.edir(slug); S = ep.short(slug); fps = ep.fps
    base = os.path.join(d, "alt", "base_full.mp4"); title = os.path.join(d, "title_4k.png"); aud = os.path.join(d, "audio_final.wav")
    punch = S.get("clean_punch", [])
    if punch and base_full_rec is not None:
        TF = int(round(T * fps)); m, _ = ep.seg_map(slug)
        owner = S.get("owner_camera")
        marks = sorted({0, TF} | {int(round(t * fps)) for a, b, z in punch for t in (a, b) if 0 < round(t * fps) < TF}
                       | {int(round(sh["out_start"] * fps)) for sh in base_full_rec["shots"] if 0 < round(sh["out_start"] * fps) < TF})
        wins = list(zip(marks[:-1], marks[1:]))
        log = []
        pieces = []                                    # (a, b, zoom filter, log entry)
        for a, b in wins:
            zq = next((z for t0, t1, z in punch if int(round(t0 * fps)) <= a < int(round(t1 * fps))), 1.0)
            zf = ""
            who = next(sh["shot"] for sh in base_full_rec["shots"] if sh["out_start"] * fps <= a < sh["out_end"] * fps)
            if owner and who != owner: zq = 1.0        # punch-ins only on the owner's own shots, never on a reaction cutaway
            if zq != 1.0:
                si = next(j for j, (a0_, a1_, n_, t0_) in enumerate(m) if int(round(t0_ * fps)) <= a < int(round(t0_ * fps)) + n_)
                fr_ = next(x for x in base_full_rec["framing"] if x["seg"] == si and x["speaker"] == who)
                z, pivot, info = resolve_punch(ep, zq, who, fr_, hook_bottom)
                cw, chh, cx, cy = punch_crop(z, pivot)
                zf = f",crop={cw}:{chh}:{cx}:{cy},scale=2160:3840:flags=lanczos,setsar=1"
                info = {"t0": round(a / fps, 2), "t1": round(b / fps, 2), **info}
            else:
                info = None
            pieces.append([a, b, zf, info])
        # coalesce neighbours with the same framing, then fold any 1-frame sliver into its neighbour: concat silently
        # dropped single-frame pieces (multicam-build clean renders came out 1-2 frames short of the audio,
        merged = []
        for p in pieces:
            if merged and merged[-1][2] == p[2]:
                merged[-1][1] = p[1]
            else:
                merged.append(p)
        i = 0
        while i < len(merged):
            if merged[i][1] - merged[i][0] == 1 and len(merged) > 1:
                if i > 0: merged[i - 1][1] = merged[i][1]
                else: merged[i + 1][0] = merged[i][0]
                del merged[i]
                if 0 < i < len(merged) and merged[i - 1][2] == merged[i][2]:
                    merged[i - 1][1] = merged[i][1]; del merged[i]
                continue
            i += 1
        log = [dict(p[3], t0=round(p[0] / fps, 2), t1=round(p[1] / fps, 2)) for p in merged if p[3]]
        fc = [f"[0:v]settb=1/25,setpts=N,split={len(merged)}" + "".join(f"[k{i}]" for i in range(len(merged)))]
        for i, (a, b, zf, _) in enumerate(merged):
            fc.append(f"[k{i}]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS{zf}[w{i}]")
        fc.append("".join(f"[w{i}]" for i in range(len(merged))) + f"concat=n={len(merged)}:v=1:a=0,settb=1/25[cam]")
        assert merged[0][0] == 0 and merged[-1][1] == TF and all(x[1] == y[0] for x, y in zip(merged, merged[1:]))
        json.dump(log, open(os.path.join(d, "clean_punch.json"), "w"), indent=1)
    else:
        fc = ["[0:v]settb=1/25,setpts=N[cam]"]
    fc += [f"[cam]ass={caps_path}[cap]", "[1:v]format=rgba,settb=1/25,setpts=N[ttl]",
           "[cap][ttl]overlay=0:0:shortest=1,format=yuv420p[vout]"]
    fpath = os.path.join(d, "filter_v6.txt")
    out = os.path.join(ep.final_dir(slug), f"{slug}.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", base, "-loop", "1", "-t", f"{T + 0.5:.2f}", "-framerate", "25", "-i", title, "-i", aud,
           "-filter_complex_script", fpath, "-map", "[vout]", "-map", "2:a"] + ENC + ["-t", f"{T:.3f}", "-movflags", "+faststart", out]
    return fc, cmd, fpath
