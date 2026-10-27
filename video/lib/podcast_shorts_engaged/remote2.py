"""REMOTE double-ender adapter with BOTH people face-tracked (config "adapter": "remote2"; for remote
interviews where both people move).

Shoot type: a remote recording. Host = the host's 4K local recording (VFR ~25 fps, picture = audio + av_offset), guest = a
1080p webcam .mov (VFR ~30 fps, fps=25 on its own branch first). Unlike reference-build (the guest sat still, so a fixed "static" crop
worked), a guest who moves around the frame needs the "tracked" treatment too: the crop follows a smoothed face track
vertically (layers.tracked_crop, the reference-build framing) AND, when the camera sets "follow_x", horizontally (sigma 0.8 s).
Works for host- and guest-owned shorts (the owner's mic is the open one, cli/audio via ep.mics()).

Per camera (episode config cameras.<k>, all measured on real stills):
  path, av_offset (picture = audio + av), vfr, src_w, src_h, column_w (crop column; = src_w with follow_x),
  face_track (episode-relative JSON {slug: [[mic_t, mouth_y, mouth_x, box_top, box_h]]}, source px),
  hair_above_box, hair_above_mouth, chin_below_mouth, base_hair_min, panel_scale, panel_mouth,
  pad_top + plate (a blurred, mirrored plate of the camera's own top rows, allowed ABOVE the source only),
  follow_x (bool), fx (optional filter after the scale, e.g. unsharp for the upscaled webcam).
Segments come from ep.seg_map (use "segment_snap": "audio": the cut edges stay on the measured silences; every branch
anchors on its camera's nearest REAL frame, <= 20 ms). Frame discipline as standard section 9.
"""
import json, os, subprocess
import numpy as np
from . import timeline as TL
from .layers import tracked_crop, _yexpr


def nearest_pts(path, t, cache):
    key = f"{os.path.basename(path)}|{t:.4f}"
    if key in cache: return cache[key]
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-read_intervals", f"{max(t - 3, 0):.3f}%{t + 1:.3f}",
                          "-show_entries", "packet=pts_time", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    pts = [float(x.strip(",")) for x in out.split() if x.strip(",") not in ("", "N/A")]
    cache[key] = min(pts, key=lambda q: abs(q - t)); return cache[key]


def x_expr(cam, track, a0, dur, w, col, cx0, sigma=0.8, step=0.2):
    r = np.array([x for x in track if a0 - 1.0 <= x[0] <= a0 + dur + 1.0])
    t, xx = r[:, 0] - a0, r[:, 2]
    nodes = np.arange(0, dur + step, step)
    xs = np.array([np.sum(xx * np.exp(-0.5 * ((t - n) / sigma) ** 2)) / np.sum(np.exp(-0.5 * ((t - n) / sigma) ** 2)) for n in nodes])
    xc = np.clip(xs - cx0 - w / 2, 0, col - w)
    return _yexpr(nodes, xc), float(xc.min()), float(xc.max())


def piece_frame(cam, rows, w0, w1, W, H, hook_bottom, margin=40):
    """STATIC full-frame crop for ONE piece of a camera (opt-in: camera "piece_static"; remote-build, "their face
    is cut off" on some of the guest's reaction cutaways). The tracked crop followed a smoothed track across the whole SEGMENT
    and lagged a guest who moves, and a cutaway that straddled a join got a second crop for its 2-6 frame sliver.
    Here every frame of the piece (full-rate face boxes: [t, xmin, xmax, top10, chin, mouth]) must fit inside ONE crop:
    the whole head (forehead landmark minus the hair/headphone allowance) below the hook (+margin), the face plus a side
    allowance for the headphones inside the width, the chin clear of the bottom. Largest scale <= max_scale that fits;
    the side allowance relaxes from `side` to `side_min` before the piece is declared unframeable.
    Returns (w, h, x0, y0, info) in the stacked (plate + source) frame; info["status"] = ok | tight | no_face | fail."""
    ps = cam["piece_static"]; pad = cam["pad_top"]; SW, SH = cam["src_w"], cam["src_h"]
    win = [r for r in rows if w0 - 0.025 <= r[0] <= w1 + 0.025]
    good = [r for r in win if r[1] is not None]
    info = {"win": [round(w0, 3), round(w1, 3)], "frames": len(win), "missing": len(win) - len(good)}
    if not good or (len(win) - len(good)) > 0.35 * len(win):
        info["status"] = "no_face"
    elif len(good) < len(win):      # a few frames without a detection (profile, laugh, hand): look at them, then list the
        info["status"] = "check"    # piece in the episode's "piece_reviewed" (the report treats a reviewed piece as passed)
        info["missing_t"] = [round(r[0], 2) for r in win if r[1] is None]
    if not good:
        return None, None, None, None, info
    a = np.array([r[1:5] for r in good], float)          # xmin xmax top chin
    fw = a[:, 1] - a[:, 0]; fh = a[:, 3] - a[:, 2]
    hair = a[:, 2] - np.maximum(cam["hair_above_box"], ps.get("hair_frac", 0.42) * fh)
    floor = max(cam["base_hair_min"], hook_bottom + margin)
    cover = H / (pad + SH)
    for side, tag in ((ps.get("side", 0.30), "ok"), (ps.get("side_min", 0.12), "tight")):
        lx = float(np.min(a[:, 0] - side * fw)); rx = float(np.max(a[:, 1] + side * fw))
        sc = ps.get("max_scale", 3.4)
        while sc >= cover - 1e-6:
            w = int(round(W / sc / 2) * 2); h = int(round(H / sc / 2) * 2)
            if h > pad + SH: h = (pad + SH) // 2 * 2; w = int(round(h * W / H / 2) * 2)
            k = H / h
            y0 = min(pad + SH - h, pad + float(hair.min()) - floor / k)
            x0 = int(round(min(max((lx + rx) / 2 - w / 2, 0), SW - w)))
            chin_out = (pad + float(a[:, 3].max()) - y0) * k
            if y0 >= 0 and lx >= x0 - 0.5 and rx <= x0 + w + 0.5 and chin_out <= H - ps.get("chin_clear", 200):
                y0 = int(round(y0))
                info.update({"status": info.get("status", tag), "scale": round(k, 4), "side": side, "x0": x0, "y0": y0,
                             "hair_out_min": round((pad + float(hair.min()) - y0) * k, 1), "crop_bottom": y0 + h, "chin_out_max": round(chin_out, 1),
                             "face_left_out": round((float(a[:, 0].min()) - x0) * k, 1),
                             "face_right_out": round((x0 + w - float(a[:, 1].max())) * k, 1)})
                return w, h, x0, y0, info
            sc -= 0.02
    info["status"] = "fail"
    return None, None, None, None, info


def plan_layer(ep, slug, layout, hook_bottom):
    S = ep.short(slug); fps = ep.fps
    m, T = ep.seg_map(slug)
    W, H = (ep.W, ep.H) if layout == "full" else (ep.W, ep.H // 2)
    TF = int(round(T * fps))
    pieces = TL.shot_pieces(m, S["shots"], fps)
    codes = [c for c in ep.c["cameras"] if any(p[1] == c for p in pieces)]
    cache_p = ep.p(ep.c.get("seek_cache", "shorts/_cache/seek_cache.json"))
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    inputs, fc, seginfo, src_lab = [], [], [], {}
    k = len(m)
    seeks = {}; piece_log = []; static_crop = {}
    for c in codes:
        cam = ep.cam(c)
        pi = len(inputs); inputs += [["-loop", "1", "-t", f"{T + 0.5:.2f}", "-framerate", "25", "-i", ep.p(cam["plate"])]]
        lab = "v" if c == ep.c.get("host_camera", "A") else "g"
        src_lab[c] = lab
        fc.append(f"[{pi}:v]split=2[{lab}pl1][{lab}pl2];[{lab}pl2]vflip[{lab}plf];[{lab}pl1][{lab}plf]vstack,gblur=sigma=1:sigmaV=14,"
                  f"settb=1/25,setpts=N,split={k}" + "".join(f"[{lab}band{i}]" for i in range(k)))
    # one input per (segment, camera): segments may be out of source order (a hook lifted from later in the episode),
    # and a shared input would buffer every frame between them
    for i, (a0, a1, n, t0) in enumerate(m):
        for c in codes:
            cam = ep.cam(c); lab = src_lab[c]
            if not any(p[0] == i and p[1] == c for p in pieces): continue
            seek = max(0.0, a0 + cam["av_offset"] - 2.0); seeks[f"{c}{i}"] = seek
            ii = len(inputs); inputs += [["-ss", f"{seek:.4f}", "-t", f"{n / fps + 3.0:.3f}", "-i", ep.p(cam["path"])]]
            fc.append(f"[{ii}:v]null[{lab}{i}]")
    cat = []
    for i, (a0, a1, n, t0) in enumerate(m):
        dur = n / fps
        mine = [p for p in pieces if p[0] == i]
        for c in codes:
            cam = ep.cam(c); lab = src_lab[c]; cnt = sum(1 for p in mine if p[1] == c)
            if not cnt:
                fc.append(f"[{lab}band{i}]nullsink"); continue
            fx = ("," + cam["fx"]) if cam.get("fx") else ""
            if layout == "full" and cam.get("piece_static"):
                p0 = nearest_pts(ep.p(cam["path"]), a0 + cam["av_offset"], cache); r0 = p0 - seeks[f"{c}{i}"]
                head = (f"[{lab}{i}]trim=start={r0 - 0.005:.4f}:end={r0 + dur + 0.3:.4f},setpts=PTS-STARTPTS,fps=25:round=near,"
                        f"settb=1/25,setpts=N,trim=end_frame={n}")
                fc.append(f"{head},crop={cam['src_w']}:{cam['src_h']}:0:0[{lab}l{i}]")
                fc.append(f"[{lab}band{i}]crop={cam['src_w']}:{cam['pad_top']}:0:0[{lab}b{i}]")
                fc.append(f"[{lab}b{i}][{lab}l{i}]vstack=shortest=1,split={cnt}" + "".join(f"[{lab}y{i}_{j}]" for j in range(cnt)))
                rows = json.load(open(ep.p(cam["piece_static"]["box_track"])))[slug]
                for j, (_, _, lo, hi) in enumerate([q for q in mine if q[1] == c]):
                    pw, ph, px, py, pinfo = piece_frame(cam, rows, a0 + lo / fps, a0 + hi / fps, W, H, hook_bottom, ep.c.get("hook_hair_margin", 40))
                    pinfo.update({"seg": i, "speaker": c, "out_start": round((TL.frames(t0, fps) + lo) / fps, 2),
                                  "out_end": round((TL.frames(t0, fps) + hi) / fps, 2)})
                    piece_log.append(pinfo)
                    if pw is None:      # unframeable: keep the render possible, the gate fails it (fix the cut, not the crop)
                        pw, ph = int(round(W / 3.0 / 2) * 2), int(round(H / 3.0 / 2) * 2); px, py = (cam["src_w"] - pw) // 2, 0
                    static_crop[(i, c, j)] = f"crop={pw}:{ph}:{px}:{py},scale={W}:{H}:flags=lanczos{fx},setsar=1"
                mine_log = [q for q in piece_log if q["seg"] == i and q["speaker"] == c]
                seginfo.append({"seg": i, "speaker": c, "src_pts": round(p0, 4), "piece_static": True, "hook_bottom": hook_bottom,
                                "hair_y_min": min((q.get("hair_out_min", 0.0) for q in mine_log), default=0.0),
                                "status": sorted({q["status"] for q in mine_log}),
                                "crop_bottom_max": max((q.get("crop_bottom", 1e9) for q in mine_log), default=1e9),
                                "source_bottom": cam["pad_top"] + cam["src_h"]})
                continue
            track = json.load(open(ep.p(cam["face_track"])))[slug]
            w, h, mx, yexpr, info = tracked_crop(cam, track, a0, dur, layout, W, H, hook_bottom, ep.c.get("hook_hair_margin", 40))
            col = cam["column_w"]; pad = cam["pad_top"]
            if cam.get("follow_x"):
                cx0 = 0; xe, xlo, xhi = x_expr(cam, track, a0, dur, w, col, cx0)
                xpart = f"'{xe}'"
            else:
                cx0 = int(min(max(mx - col / 2, 0), cam["src_w"] - col)); xpart = str(max(0, min(int(round(mx - cx0 - w / 2)), col - w)))
            p0 = nearest_pts(ep.p(cam["path"]), a0 + cam["av_offset"], cache); r0 = p0 - seeks[f"{c}{i}"]
            if cam.get("vfr_resample"):    # webcam: trim on real time, then fps=25 on its own branch (standard section 9)
                head = (f"[{lab}{i}]trim=start={r0 - 0.005:.4f}:end={r0 + dur + 0.3:.4f},setpts=PTS-STARTPTS,fps=25:round=near,"
                        f"settb=1/25,setpts=N,trim=end_frame={n}")
            else:
                head = f"[{lab}{i}]trim=start={r0 - 0.015:.4f}:end={r0 + dur + 0.2:.4f},settb=1/25,setpts=N,trim=end_frame={n}"
            fc.append(f"{head},crop={col}:{cam['src_h']}:{cx0}:0[{lab}l{i}]")
            fc.append(f"[{lab}band{i}]crop={col}:{pad}:{cx0}:0[{lab}b{i}]")
            fc.append(f"[{lab}b{i}][{lab}l{i}]vstack=shortest=1,crop={w}:{h}:{xpart}:'{yexpr}',scale={W}:{H}:flags=lanczos{fx},setsar=1,split={cnt}"
                      + "".join(f"[{lab}x{i}_{j}]" for j in range(cnt)))
            if layout == "full": seginfo.append({"seg": i, "speaker": c, "src_pts": round(p0, 4), **info})
        used = {c: 0 for c in codes}
        for (_, s, lo, hi) in mine:
            lab = f"pc{len(cat)}"; cat.append(lab)
            if (i, s, used[s]) in static_crop:
                fc.append(f"[{src_lab[s]}y{i}_{used[s]}]trim=start_frame={lo}:end_frame={hi},setpts=PTS-STARTPTS,{static_crop[(i, s, used[s])]}[{lab}]")
            else:
                fc.append(f"[{src_lab[s]}x{i}_{used[s]}]trim=start_frame={lo}:end_frame={hi},setpts=PTS-STARTPTS[{lab}]")
            used[s] += 1
    fc.append("".join(f"[{c}]" for c in cat) + f"concat=n={len(cat)}:v=1:a=0,settb=1/25,{ep.c['grade']},format=yuv420p[vout]")
    json.dump(cache, open(cache_p, "w"), indent=0)
    d = ep.altdir(slug); fpath = os.path.join(d, f"filter_base_{layout}.txt"); out = os.path.join(d, f"base_{layout}.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y"] + [x for g in inputs for x in g] + [
        "-filter_complex_script", fpath, "-map", "[vout]", "-c:v", "libx264", "-preset", "medium", "-crf", "12",
        "-pix_fmt", "yuv420p", "-r", "25", "-fps_mode", "cfr", "-t", f"{T:.3f}", "-an", out]
    rec = {"slug": slug, "layout": layout, "duration": T, "frames": TF, "seeks": seeks, "shots": TL.shot_log(m, pieces, fps), "framing": seginfo, "piece_framing": piece_log}
    return fc, cmd, rec, fpath

