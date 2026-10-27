"""Stage 1: the two clean, graded CAMERA layers per short.

  base_full   2160x3840  full-frame layout: the approved edit's shot list (speaker + listener reaction cutaways)
  base_panel  2160x1920  the same shots framed for the BOTTOM panel of a split

CAMERA ADAPTER. Two camera kinds are supported, both measured per episode and stored in the episode config:
  "tracked"  a studio camera followed by a smoothed face-track (mouth row) with an optional blurred, mirrored wall plate
             above the source (reference-build: the host's 4K local recording .mov, VFR, picture = audio + av_offset)
  "static"   a fixed crop of a webcam (reference-build: the guest's 1080p webcam, VFR ~29.97 -> fps=25 on its own branch)
A new setup needs its own measured geometry; the filter discipline below does not change.

IN-PERSON MULTICAM (multicam.plan_layer, first built on the multicam build, config "camera_mode": "in_person_multicam"): every
person is a "tracked" camera entry (their own camera file, or a column of a shared two-shot), with a YuNet face track
per short ({person: {slug: [[mic_t, mouth_y, mouth_x, box_top, box_h]]}}), measured hair/chin offsets, an optional wall
plate above the source (pad_top 0 = none), a column range (column_x) that keeps the crop on that person, and a sync
entry (sync.py). The short's OWNER camera defines the frame grid (ep.seg_map); every other camera is trimmed per
segment at its own exact sync time (nearest real frame of a CFR 25p source: error <= 20 ms). Works for host- and
guest-owned shorts alike.

FRAME DISCIPLINE (the reference-build v3 stutter post-mortem; never relax): each live branch is trimmed on real time, renumbered
1:1 at 25p straight after the trim (settb=1/25, setpts=N, trim=end_frame=n), every vstack/overlay input has settb=1/25,
joins use shortest=1, and nothing is renumbered after a multi-input filter. Segment starts anchor on the REAL nearest
source frame (ffprobe), not the nominal grid.
"""
import json, os, subprocess
import numpy as np
from . import timeline as TL


def nearest_frame_pts(mov, t):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-read_intervals", f"{t - 4:.3f}%{t + 1:.3f}",
                          "-show_entries", "frame=pts_time", "-of", "csv=p=0", mov], capture_output=True, text=True).stdout
    pts = [float(x.strip(",")) for x in out.split() if x.strip(",")]
    return min(pts, key=lambda p: abs(p - t))


def mouth_curve(track, a0, dur, sigma=0.35, step=0.2):
    r = np.array([x for x in track if a0 - 1.0 <= x[0] <= a0 + dur + 1.0])
    t, y, xx = r[:, 0] - a0, r[:, 1], r[:, 2]
    nodes = np.arange(0, dur + step, step)
    ys = np.array([np.sum(y * np.exp(-0.5 * ((t - n) / sigma) ** 2)) / np.sum(np.exp(-0.5 * ((t - n) / sigma) ** 2)) for n in nodes])
    return nodes, ys, float(np.median(xx))


def _yexpr(nodes, yc):
    terms = []
    for k in range(len(nodes) - 1):
        t0, t1, v0, v1 = nodes[k], nodes[k + 1], yc[k], yc[k + 1]
        terms.append(f"between(t\\,{t0:.2f}\\,{t1:.2f}-0.0001)*({v0:.1f}+({v1 - v0:.2f})*(t-{t0:.2f})/{t1 - t0:.2f})")
    terms.append(f"gte(t\\,{nodes[-1]:.2f})*{yc[-1]:.1f}")
    return "+".join(terms)


def hair_floor(cam, hook_bottom, margin=40):
    """hair row floor in the un-punched full frame: the measured base, or lower if the hook card needs it"""
    return max(cam["base_hair_min"], hook_bottom + margin)


def full_seg_geometry(cam, m_max, hook_bottom, d_max=None, out_h=3840, margin=40):
    """Full-frame tracked framing : the HIGHEST mouth row that still covers the bottom edge
    with real picture at the segment's lowest mouth AND keeps the hair below the hook. d_max = the segment's largest
    mouth-to-hair distance from the face track (box top - hair_above_box), never less than the measured constant.
    s = (H - hair_min) / (src_h - m_max + d) ; mouth_y = hair_min + d * s"""
    hm = hair_floor(cam, hook_bottom, margin)
    dd = cam["hair_above_mouth"] if d_max is None else max(cam["hair_above_mouth"], d_max)
    s = (out_h - hm) / (cam["src_h"] - m_max + dd)
    return s, hm + dd * s


def static_full_crop(cam, hook_bottom, out_w=2160, out_h=3840, margin=40, base_hair_min=670):
    """Full-frame static (webcam) crop : fill top-to-bottom from the source, bottom edge =
    the source bottom, face centred, the largest scale <= full_scale that keeps the highest hair row below the hook."""
    hm = max(base_hair_min, hook_bottom + margin)
    sc = min(cam["full_scale"], (out_h - hm) / (cam["src_h"] - cam["hair_y_src"]))
    while True:   # step down until the ROUNDED (even-pixel) crop really puts the hair at/below hm
        w = int(round(out_w / sc / 2) * 2); h = int(round(out_h / sc / 2) * 2); y0 = cam["src_h"] - h
        if (cam["hair_y_src"] - y0) * out_h / h >= hm: break
        sc -= 0.005
    return out_h / h, w, h, int(round(cam["face_cx_src"] - w / 2)), y0


def chin_on_centre_feasible(cam, m_max, out_h=3840, hook_clear=570):
    """Which scales allow chin-on-centre with a covered bottom and the hair clear of the hook (reference-build: none -> fallback,
    captions over the mouth). chin: mouth <= C - chin*s ; bottom: mouth >= H - s*(src_h - m_max) ; hair: mouth >= clear + 20 + hair*s"""
    C = out_h / 2 - 70
    sols = []
    for k in range(100, 500):
        s = k / 100
        lo = max(out_h - s * (cam["src_h"] - m_max), hook_clear + 20 + cam["hair_above_mouth"] * s)
        hi = C - cam["chin_below_mouth"] * s
        if lo <= hi: sols.append(s)
    return sols


def tracked_crop(cam, track, a0, dur, layout, W, H, hook_bottom=None, margin=40, static=False):
    """static=True (opt-in per short, "static_camera": multicam-build: "on a podcast short, the moving of the
    camera isn't great"): ONE fixed crop per segment instead of following the mouth - the segment's median framing,
    clamped so the hair clears the hook (+margin) at every tracked moment and the bottom edge stays covered."""
    if not any(a0 - 1.0 <= x[0] <= a0 + dur + 1.0 for x in track):
        raise SystemExit(f"face track has no rows for {cam.get('who')} at {a0:.2f}+{dur:.2f}: re-run the tracker")
    nodes, ys, mx = mouth_curve(track, a0, dur)
    pad = cam["pad_top"]
    if layout == "full":
        tr = np.array([r for r in track if a0 - 0.1 <= r[0] <= a0 + dur + 0.1])
        if tr.ndim < 2 or len(tr) == 0:     # remote-build: no detection inside a very short segment (hand over the face) -> the +-1 s rows
            tr = np.array([r for r in track if a0 - 1.0 <= r[0] <= a0 + dur + 1.0])
        ys_at = np.interp(tr[:, 0] - a0, nodes, ys); hair_src = tr[:, 3] - cam["hair_above_box"]
        d_max = float(np.max(ys_at - hair_src))
        sc, mouth_y = full_seg_geometry(cam, float(ys.max()) + 2.0, hook_bottom, d_max, H, margin)
    else:
        sc, mouth_y = cam["panel_scale"], cam["panel_mouth"]
    w = int(round(W / sc / 2) * 2); h = int(round(H / sc / 2) * 2)
    ymax = pad + cam["src_h"] - h
    yc = np.clip(pad + ys - mouth_y / sc, 0, ymax)
    if static:
        lim = ymax
        if layout == "full" and hook_bottom is not None:
            lim = min(lim, pad + float(hair_src.min()) - (hook_bottom + margin) / sc)
        y0 = float(np.clip(np.median(yc), 0, max(0.0, lim)))
        if layout == "full":
            hair_out = sc * (pad + hair_src - y0)
            info = {"scale": round(sc, 4), "mouth_y": round(float(np.median(sc * (pad + ys - y0))), 1), "static": True,
                    "hair_y_min": round(float(hair_out.min()), 1), "hook_bottom": hook_bottom,
                    "hair_clearance_min": round(float(hair_out.min()) - hook_bottom, 1) if hook_bottom is not None else None,
                    "crop_bottom_max": round(y0 + h, 1), "source_bottom": pad + cam["src_h"]}
        else:
            info = {"static": True}
        return w, h, mx, f"{y0:.2f}", info
    if layout == "full":
        hair_out = mouth_y - sc * (ys_at - hair_src)
        info = {"scale": round(sc, 4), "mouth_y": round(mouth_y, 1), "hair_y_min": round(float(hair_out.min()), 1),
                "hook_bottom": hook_bottom, "hair_clearance_min": round(float(hair_out.min()) - hook_bottom, 1),
                "crop_bottom_max": round(float(yc.max()) + h, 1), "source_bottom": pad + cam["src_h"]}
    else:
        info = {}
    return w, h, mx, _yexpr(nodes, yc), info


def plan(ep, slug, layout, hook_bottom, dry_seek_cache=None):
    """Build the filter graph + ffmpeg command for one camera layer. Returns (fc_list, cmd, json_record)."""
    if ep.c.get("camera_mode") == "in_person_multicam":       # multicam-build+: see multicam.py
        from .multicam import plan_layer
        return plan_layer(ep, slug, layout, hook_bottom)
    if ep.c.get("adapter") == "remote2":                        # remote2: remote, both people face-tracked, see remote2.py
        from .remote2 import plan_layer as plan_remote2
        return plan_remote2(ep, slug, layout, hook_bottom)
    if ep.c.get("adapter") == "face4k":                         # face4k-build: own 4K cams incl. VFR iPhone, see face4k.py
        from .face4k import plan_layer as plan_face4k
        return plan_face4k(ep, slug, layout, hook_bottom)
    S = ep.short(slug); fps = ep.fps
    m, T = TL.seg_map(S["segs"], fps, ep.v_start, ep.av)
    W, H = (ep.W, ep.H) if layout == "full" else (ep.W, ep.H // 2)
    A = ep.host_cam; G = ep.c["cameras"][ep.c.get("other_camera", "S")]
    hc, gc = ep.c.get("host_camera", "A"), ep.c.get("other_camera", "S")
    AV, VS = A["av_offset"], A["v_start"]
    mov = ep.p(A["path"]); gmov = ep.p(G["path"])
    track = json.load(open(ep.p(A["face_track"])))[slug]
    S_seek = m[0][0] + AV - 2.0 - 0.02
    S_seek = VS + round((S_seek - VS) * fps) / fps - 0.02
    G_seek = m[0][0] - 2.0
    span = m[-1][1] + AV - S_seek + 1.0
    TF = int(round(T * fps))
    pieces = TL.shot_pieces(m, S["shots"], fps)
    col = A["column_w"]; pad = A["pad_top"]
    k = len(m); fc = []; cat = []; seginfo = []
    fc.append(f"[0:v]split={k}" + "".join(f"[v{i}]" for i in range(k)))
    fc.append(f"[1:v]split={k}" + "".join(f"[g{i}]" for i in range(k)))
    fc.append(f"[2:v]split=2[pl1][pl2];[pl2]vflip[plf];[pl1][plf]vstack,gblur=sigma=1:sigmaV=14,settb=1/25,setpts=N,split={k}"
              + "".join(f"[band{i}]" for i in range(k)))
    for i, (a0, a1, n, t0) in enumerate(m):
        dur = n / fps
        mine = [p for p in pieces if p[0] == i]
        na = sum(1 for p in mine if p[1] == hc); ns = sum(1 for p in mine if p[1] == gc)
        if na:
            w, h, mx, yexpr, info = tracked_crop(A, track, a0, dur, layout, W, H, hook_bottom, ep.c.get("hook_hair_margin", 40))
            cx0 = int(min(max(mx - col / 2, 0), A["src_w"] - col)); x = max(0, min(int(round(mx - cx0 - w / 2)), col - w))
            p0 = (dry_seek_cache or {}).get((slug, i)) or nearest_frame_pts(mov, a0 + AV); r0 = p0 - S_seek
            if dry_seek_cache is not None: dry_seek_cache[(slug, i)] = p0
            fc.append(f"[v{i}]trim=start={r0 - 0.015:.4f}:end={r0 + dur + 0.2:.4f},settb=1/25,setpts=N,trim=end_frame={n},crop={col}:{A['src_h']}:{cx0}:0[l{i}]")
            fc.append(f"[band{i}]crop={col}:{pad}:{cx0}:0[b{i}]")
            fc.append(f"[b{i}][l{i}]vstack=shortest=1,crop={w}:{h}:{x}:'{yexpr}',scale={W}:{H}:flags=lanczos,setsar=1,split={na}"
                      + "".join(f"[ax{i}_{j}]" for j in range(na)))
            if layout == "full": seginfo.append({"seg": i, "speaker": hc, **info})
        else:
            fc.append(f"[v{i}]nullsink"); fc.append(f"[band{i}]nullsink")
        if ns:
            g0 = a0 - G_seek
            if layout == "full":
                ssc, cw, ch, cxs, cys = static_full_crop(G, hook_bottom, ep.W, ep.H, ep.c.get("hook_hair_margin", 40), A["base_hair_min"])
            else:
                cw, ch, cxs, cys = G["panel_crop"]
            fc.append(f"[g{i}]trim=start={g0:.4f}:end={g0 + dur + 0.3:.4f},setpts=PTS-STARTPTS,fps=25:round=near,settb=1/25,setpts=N,trim=end_frame={n},"
                      f"crop={cw}:{ch}:{cxs}:{cys},scale={W}:{H}:flags=lanczos,{G['fx']},setsar=1,split={ns}"
                      + "".join(f"[st{i}_{j}]" for j in range(ns)))
            if layout == "full":
                hair = (G["hair_y_src"] - cys) * H / ch
                seginfo.append({"seg": i, "speaker": gc, "scale": round(ssc, 4), "crop": [cw, ch, cxs, cys], "hair_y_min": round(hair),
                                "hair_clearance_min": round(hair - hook_bottom, 1), "mouth_y": round((G["mouth_y_src"] - cys) * H / ch),
                                "crop_bottom": cys + ch, "source_bottom": G["src_h"]})
        else:
            fc.append(f"[g{i}]nullsink")
        ca = cs = 0
        for (_, s, lo, hi) in mine:
            src = f"[ax{i}_{ca}]" if s == hc else f"[st{i}_{cs}]"
            if s == hc: ca += 1
            else: cs += 1
            lab = f"pc{len(cat)}"; cat.append(lab)
            fc.append(f"{src}trim=start_frame={lo}:end_frame={hi},setpts=PTS-STARTPTS[{lab}]")
    fc.append("".join(f"[{c}]" for c in cat) + f"concat=n={len(cat)}:v=1:a=0,settb=1/25,{ep.c['grade']},format=yuv420p[vout]")
    d = ep.altdir(slug); fpath = os.path.join(d, f"filter_base_{layout}.txt"); out = os.path.join(d, f"base_{layout}.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{S_seek:.4f}", "-t", f"{span:.3f}", "-i", mov,
           "-ss", f"{G_seek:.4f}", "-t", f"{span:.3f}", "-i", gmov,
           "-loop", "1", "-t", f"{T + 0.5:.2f}", "-framerate", "25", "-i", ep.p(A["plate"]),
           "-filter_complex_script", fpath, "-map", "[vout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p", "-r", "25", "-fps_mode", "cfr",
           "-t", f"{T:.3f}", "-an", out]
    rec = {"slug": slug, "layout": layout, "duration": T, "frames": TF, "seek": S_seek, "guest_seek": G_seek,
           "shots": [{k2: v for k2, v in x.items()} for x in TL.shot_log(m, pieces, fps)], "framing": seginfo}
    return fc, cmd, rec, fpath
