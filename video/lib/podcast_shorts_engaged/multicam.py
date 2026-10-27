"""In-person MULTICAM adapter (config "camera_mode": "in_person_multicam"; first built on an in-person three-camera episode).

Three or more people, each a "tracked" camera entry (their own camera file, or a column of a shared two-shot), all
mics on one clock (mic time). Kept in its own module so it does not collide with the two-person in-person work in
config.py / audio.py (adapter "inperson_multicam", face4k-build). Spec: PODCAST-SHORTS-ENGAGEMENT-FORMAT.md.

  seg_map(ep, slug)   segments snapped to the short's OWNER camera grid (S["av"], S["v_start"], written by the episode's
                      make_config.py from the sync model), falling back to the episode's own seg_map
  plan_layer(...)     the camera layer graph (full 2160x3840 or panel 2160x1920): per (segment, person) a branch trimmed
                      at that person's exact sync time (nearest real frame of a CFR 25p source, <= 20 ms), cropped by
                      the reference-build tracked framing (layers.tracked_crop) inside the person's column, with an optional mirrored
                      wall plate above the source; then the shot pieces, concat, grade. Frame discipline as layers.py.
  plan_audio(...)     owner mic open for the whole short (minus S["owner_mute_windows"]); every listener mic completely
                      muted except S["mic_windows"][mic] (IN-PERSON-AUDIO.md: 0.01 s ramps); per-segment cut, 40 ms equal-power
                      crossfade centred on every internal join (audio.join_crossfade), 10 / 45 ms head / tail fades,
                      bus compression, limiter (then audio.run loudnorms).
Camera keys: kind=tracked, path, sync_off, sync_extra, lead0, ppm (sync.py), src_w, src_h, face_track, hair_above_box,
hair_above_mouth, chin_below_mouth, base_hair_min, panel_scale, panel_mouth, column_w, column_x, pad_top, plate, disabled.
"""
import json, os
from . import sync as SY
from . import timeline as TL
from .layers import tracked_crop
from .audio import gate_expr


def seg_map(ep, slug):
    S = ep.short(slug)
    if "av" in S: return TL.seg_map(S["segs"], ep.fps, S.get("v_start", 0.0), S["av"])
    return ep.seg_map(slug)


def plan_layer(ep, slug, layout, hook_bottom):
    """In-person multicam camera layer (see the module docstring). Returns (fc_list, cmd, json_record, filter_path)."""
    S = ep.short(slug); fps = ep.fps
    m, T = seg_map(ep, slug)
    W, H = (ep.W, ep.H) if layout == "full" else (ep.W, ep.H // 2)
    pieces = TL.shot_pieces(m, S["shots"], fps)
    margin = ep.c.get("hook_hair_margin", 40)
    cams = ep.c["cameras"]
    tracks_all = {}
    pairs = []                                    # (seg, code) in graph order
    for i in range(len(m)):
        for p in pieces:
            if p[0] == i and (i, p[1]) not in pairs: pairs.append((i, p[1]))
    # inputs: one per camera FILE (a shared two-shot feeds two people), seeked on that file's real 25p grid
    files = []
    for i, c in pairs:
        f = cams[c]["path"]
        if f not in files: files.append(f)
    seeks, spans = {}, {}
    for f in files:
        ts = [(SY.cam_time(ep, c, m[i][0]), SY.cam_time(ep, c, m[i][1])) for i, c in pairs if cams[c]["path"] == f]
        s0 = min(t[0] for t in ts) - 2.0
        seeks[f] = round(s0 * fps) / fps - 0.02
        spans[f] = max(t[1] for t in ts) - seeks[f] + 1.0
    plates = [c for c in dict.fromkeys(c for _, c in pairs) if cams[c].get("pad_top", 0) > 0]
    inputs = [["-ss", f"{seeks[f]:.4f}", "-t", f"{spans[f]:.3f}", "-i", ep.p(f)] for f in files]
    inputs += [["-loop", "1", "-t", f"{T + 0.5:.2f}", "-framerate", "25", "-i", ep.p(cams[c]["plate"])] for c in plates]
    fc = []
    uses = {f: sum(1 for _, c in pairs if cams[c]["path"] == f) for f in files}
    for k, f in enumerate(files):
        fc.append(f"[{k}:v]split={uses[f]}" + "".join(f"[in{k}_{j}]" for j in range(uses[f])))
    for q, c in enumerate(plates):
        nu = sum(1 for _, cc in pairs if cc == c)
        fc.append(f"[{len(files) + q}:v]split=2[pa{q}][pb{q}];[pb{q}]vflip[pf{q}];[pa{q}][pf{q}]vstack,gblur=sigma=1:sigmaV=14,"
                  f"settb=1/25,setpts=N,split={nu}" + "".join(f"[band{c}_{j}]" for j in range(nu)))
    used_in = {f: 0 for f in files}; used_band = {c: 0 for c in plates}
    seginfo, syncrec, branch = [], [], {}
    for i, c in pairs:
        a0, a1, n, t0 = m[i]; dur = n / fps; cam = cams[c]
        for d0, d1 in cam.get("disabled", []):
            if a1 > d0 and a0 < d1: raise SystemExit(f"{slug}: camera {c} is disabled over mic {d0}-{d1}")
        if c not in tracks_all: tracks_all[c] = json.load(open(ep.p(cam["face_track"])))[c][slug]
        w, h, mx, yexpr, info = tracked_crop(cam, tracks_all[c], a0, dur, layout, W, H, hook_bottom, margin,
                                             static=bool(ep.short(slug).get("static_camera")))
        if h > cam.get("pad_top", 0) + cam["src_h"]:
            raise SystemExit(f"{slug} seg {i} {c} {layout}: crop {h} px is taller than plate + source "
                             f"({cam.get('pad_top', 0)} + {cam['src_h']}): give this camera a taller wall plate (pad_top)")
        col = cam["column_w"]; xlo, xhi = cam.get("column_x", [0, cam["src_w"]])
        cx0 = int(min(max(mx - col / 2, xlo), xhi - col)); x = max(0, min(int(round(mx - cx0 - w / 2)), col - w))
        f = cam["path"]; k = files.index(f); j = used_in[f]; used_in[f] += 1
        t_src = SY.cam_time(ep, c, a0); p0 = round(t_src * fps) / fps; r0 = p0 - seeks[f]
        syncrec.append({"seg": i, "cam": c, "mic_in": round(a0, 4), "src_exact": round(t_src, 4), "src_frame": round(p0, 3),
                        "delta_ms": round((p0 - t_src) * 1000, 1)})
        lab = f"c{i}{c}"
        fc.append(f"[in{k}_{j}]trim=start={r0 - 0.015:.4f}:end={r0 + dur + 0.2:.4f},settb=1/25,setpts=N,trim=end_frame={n},"
                  f"crop={col}:{cam['src_h']}:{cx0}:0[l{lab}]")
        npc = sum(1 for p in pieces if p[0] == i and p[1] == c)
        tail = f"crop={w}:{h}:{x}:'{yexpr}',scale={W}:{H}:flags=lanczos,setsar=1,split={npc}" + "".join(f"[{lab}_{q}]" for q in range(npc))
        if cam.get("pad_top", 0) > 0:
            jb = used_band[c]; used_band[c] += 1
            fc.append(f"[band{c}_{jb}]crop={col}:{cam['pad_top']}:{cx0}:0[b{lab}]")
            fc.append(f"[b{lab}][l{lab}]vstack=shortest=1," + tail)
        else:
            fc.append(f"[l{lab}]" + tail)
        branch[(i, c)] = [lab, 0]
        if layout == "full": seginfo.append({"seg": i, "speaker": c, **info})
    cat = []
    for (i, c, lo, hi) in pieces:
        lab, q = branch[(i, c)]; branch[(i, c)][1] += 1
        pl = f"pc{len(cat)}"; cat.append(pl)
        fc.append(f"[{lab}_{q}]trim=start_frame={lo}:end_frame={hi},setpts=PTS-STARTPTS[{pl}]")
    fc.append("".join(f"[{c}]" for c in cat) + f"concat=n={len(cat)}:v=1:a=0,settb=1/25,{ep.c['grade']},format=yuv420p[vout]")
    d = ep.altdir(slug); fpath = os.path.join(d, f"filter_base_{layout}.txt"); out = os.path.join(d, f"base_{layout}.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y"] + [x for i in inputs for x in i] + [
           "-filter_complex_script", fpath, "-map", "[vout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p", "-r", "25", "-fps_mode", "cfr",
           "-t", f"{T:.3f}", "-an", out]
    rec = {"slug": slug, "layout": layout, "duration": T, "frames": int(round(T * fps)), "seeks": seeks, "seek": seeks[files[0]],
           "shots": TL.shot_log(m, pieces, fps), "framing": seginfo, "sync": syncrec}
    return fc, cmd, rec, fpath


def plan_audio(ep, slug, raw_out):
    S = ep.short(slug); fps = ep.fps; ramp = ep.c["audio"].get("gate_ramp", 0.01)
    m, T = seg_map(ep, slug)
    seekA = m[0][0] - 2.0; span = m[-1][1] - seekA + 2.0
    own = S["owner_mic"]; wins = {k: v for k, v in S.get("mic_windows", {}).items() if v and k != own}
    mics = [own] + list(wins)
    mute = S.get("owner_mute_windows", [])
    fc = []
    for q, mic in enumerate(mics):
        if q == 0: e = "1" if not mute else f"max(0\\,1-({gate_expr(mute, seekA, 1.0, ramp)}))"
        else: e = gate_expr(wins[mic], seekA, 1.0, ramp)
        fc.append(f"[{q}:a]asetnsamples=n=96,volume='{e}':eval=frame[g{q}]")
    k = len(m); N = len(mics)
    for q in range(N):
        fc.append(f"[g{q}]asplit={k}" + "".join(f"[g{q}s{i}]" for i in range(k)))
    xf = ep.c["audio"].get("join_crossfade", 0.04); h = xf / 2
    for i, (a0, a1, n, t0) in enumerate(m):
        # internal joins: each side extended by h past the join and equal-power crossfaded over 2h, centred on the join
        # (the approved multicam-build cuts sit inside sound; a hard 20 ms fade-out/in leaves a dip). Length and sync unchanged.
        el = h if i > 0 else 0.0; er = h if i < k - 1 else 0.0
        r0, r1 = a0 - seekA - el, a0 - seekA + n / fps + er; dur = r1 - r0
        for q in range(N):
            fc.append(f"[g{q}s{i}]atrim=start={r0:.5f}:end={r1:.5f},asetpts=PTS-STARTPTS[t{q}s{i}]")
        mix = "".join(f"[t{q}s{i}]" for q in range(N)) + (f"amix=inputs={N}:normalize=0," if N > 1 else "anull,")
        fx = []
        if i == 0: fx.append("afade=t=in:st=0:d=0.010")
        if i == k - 1: fx.append(f"afade=t=out:st={dur - 0.045:.4f}:d=0.045")
        fc.append(mix + (",".join(fx) if fx else "anull") + f"[s{i}]")
    cur = "s0"
    for i in range(1, k):
        nxt = f"x{i}"
        fc.append(f"[{cur}][s{i}]acrossfade=d={xf}:c1=qsin:c2=qsin[{nxt}]"); cur = nxt
    fc.append(f"[{cur}]aformat=sample_rates=48000:channel_layouts=mono,"
              "acompressor=threshold=0.063:ratio=2.5:attack=8:release=150:makeup=2,"
              "alimiter=limit=0.35:attack=3:release=60:level=false[mix]")
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for mic in mics:
        cmd += ["-ss", f"{seekA:.4f}", "-t", f"{span:.3f}", "-i", ep.p(ep.c["audio"]["mics"][mic])]
    return cmd + ["-filter_complex", ";".join(fc), "-map", "[mix]", "-c:a", "pcm_s24le", raw_out]
