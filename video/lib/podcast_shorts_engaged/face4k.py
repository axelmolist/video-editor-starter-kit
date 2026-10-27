"""IN-PERSON MULTICAM adapter, "face4k" kind (config "adapter": "face4k"; first built on an in-person episode with own 4K cameras).

Shoot type: everyone on their own 4K camera (CFR or VFR, any display rotation that ffmpeg autorotates), two isolated
mics on one clock ("mic time" = host-audio time), each camera synced by its own LINEAR drift model
(cam_time = t + slope*t + intercept, cameras.<k>.sync), host- OR guest-owned shorts. Everything here is self-contained
so the multicam-build multicam work (layers.plan_multicam, camera_mode "in_person_multicam") and this adapter never edit each
other's code; the shared modules only dispatch here (layers.plan, cli words/audio).

CAMERA GEOMETRY (per camera, source pixels, measured on real 4K stills and stored in the episode config):
  hair_above_box     YuNet face-box top minus the real hair top          hair_above_mouth  floor for mouth-to-hair
  chin_below_mouth   mouth row to chin (rounded up)                       full_scale_max    upscale-quality cap
  panel_scale, panel_hair_y   bottom-panel scale + hair row in the 2160x1920 panel
  pad_top            rows of a blurred mirror of the camera's OWN top rows allowed above the source (never below)
  vfr                true -> fps=25 on the camera's own branch first (standard section 9)
FACE TRACK  ep.c["face_track"]: {cam: {slug: [[mic_t, mouth_y, mouth_x, box_top, box_h, box_cx], ...]}} at 5 fps over
            every segment +-1 s (track_faces.py).

FULL-FRAME FRAMING (standard section 7, chin-led): the largest scale <= full_scale_max that puts the chin on the chin
line (default H/2 - 70 = just above the fixed caption row, so captions sit UNDER the chin), keeps the highest hair
row >= hook bottom + 40 px over the whole segment and keeps the crop inside the (padded) source; if no scale does
(face4k-build: the host sits high in the joint frame under a TWO-line hook), the smallest scale that keeps the hair clear with the
crop top-anchored (chin_fallback: the chin drops toward the caption row, the standard's accepted fallback). The crop follows the smoothed mouth row (sigma 0.35 s) and, slowly,
the face centre (sigma 0.8 s). Bottom edge: always real picture (gate). Wide in-person shots have picture to spare
below the face, so unlike reference-build the chin-on-centre framing IS feasible; the mouth fallback is not needed.

AUDIO (IN-PERSON-AUDIO.md reconciled with standard section 8): the OWNER's mic open, the other mic fully muted except
its reply windows; ramps exactly 0.01 s (480 samples, sample clock, built in numpy); the owner's mic is ALSO muted
inside the reply windows (owner_mic_mute_windows, default = the reply windows) so its delayed spill of the reply does
not double it - windows are authored in silence on the owner's mic, so no owner sound is ever muted. 10/20/45 ms edge
fades, the reference-build bus (compressor + limiter) and two-pass linear loudnorm (audio.run).
"""
import json, os, subprocess
import numpy as np
from . import timeline as TL
from .layers import _yexpr
from .captions import to_locale     # British spelling on the printed words

SR = 48000


# ------------------------------------------------------------------------------------------------ camera layers
def nearest_pts_packets(path, t, cache=None):
    """nearest real frame pts to t (packet pts: no decode; right for CFR and VFR). Cached per (file, t)."""
    key = f"{os.path.basename(path)}|{t:.4f}"
    if cache is not None and key in cache: return cache[key]
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-read_intervals", f"{max(t - 3, 0):.3f}%{t + 1:.3f}",
                          "-show_entries", "packet=pts_time", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    pts = [float(x.strip(",")) for x in out.split() if x.strip(",") not in ("", "N/A")]
    p = min(pts, key=lambda q: abs(q - t))
    if cache is not None: cache[key] = p
    return p


def _smooth(t, v, nodes, sigma):
    wts = np.exp(-0.5 * ((t[None, :] - nodes[:, None]) / sigma) ** 2)
    return (wts * v[None, :]).sum(1) / wts.sum(1)


def face_geometry(cam, rows, a0, dur, layout, W, H, hook_bottom, margin=40, chin_line=None, step=0.2, arrays=False):
    """Framing for one (segment, camera) from that camera's face track -> (w, h, xexpr, yexpr, col_x0, col_w, info)
    (+ (nodes, crop_x, crop_y) in padded-source pixels when arrays=True: stills use exactly the planned crop)."""
    r = np.array([x for x in rows if a0 - 1.0 <= x[0] <= a0 + dur + 1.0])
    if len(r) < 3: raise SystemExit(f"face track too thin for {cam['who']} at mic {a0:.2f} ({len(r)} rows): re-run track_faces.py")
    t, my, bt, bcx = r[:, 0] - a0, r[:, 1], r[:, 3], r[:, 5]
    nodes = np.arange(0, dur + step, step)
    ys = _smooth(t, my, nodes, 0.35); xs_c = _smooth(t, bcx, nodes, 0.8)
    ys_at = np.interp(t, nodes, ys); hair_src = bt - cam["hair_above_box"]
    D = max(cam["hair_above_mouth"], float(np.max(ys_at - hair_src)))
    pad = cam.get("pad_top", 0); chin = cam["chin_below_mouth"]
    fallback = False
    if layout == "full":
        # mouth row m (constant in the output; the crop follows the mouth) at scale s must satisfy:
        #   hair:  m >= hm + s*D        chin on the chin line:  m <= C - chin*s        crop top inside the padded
        #   source at every node:  m <= s*(pad + min mouth row)
        # -> the LARGEST s <= full_scale_max meeting all three (chin-led, captions under the chin); if none exists
        # (head high in a wide shot + a two-line hook), the SMALLEST s meeting hair + crop top, top-anchored (the chin
        # drops toward / below the caption row: the standard's accepted fallback).
        C = chin_line if chin_line is not None else H / 2 - 70
        hm = max(cam.get("base_hair_min", 0), hook_bottom + margin)
        ysmin = float(ys.min()); cap = cam["full_scale_max"]; sc = None
        for k in range(int(cap * 1000), 999, -5):
            s_ = k / 1000
            if hm + s_ * D <= min(C - chin * s_, s_ * (pad + ysmin)): sc = s_; mouth_y = min(C - chin * s_, s_ * (pad + ysmin)); break
        if sc is None:
            fallback = True
            sc = min(cap, hm / max(pad + ysmin - D, 1e-6)); mouth_y = sc * (pad + ysmin)
    else:
        sc = cam["panel_scale"]; mouth_y = cam["panel_hair_y"] + D * sc
    w = int(round(W / sc / 2) * 2); h = int(round(H / sc / 2) * 2)
    ymax = pad + cam["src_h"] - h
    yc = np.clip(pad + ys - mouth_y / sc, 0, ymax)
    xl = np.clip(xs_c - w / 2, 0, cam["src_w"] - w)
    col_x0 = int(max(0, np.floor(xl.min()) - 16)) // 2 * 2
    col_w = min(cam["src_w"] - col_x0, int(np.ceil(xl.max())) + w + 16 - col_x0) // 2 * 2
    yc_at = np.interp(t, nodes, yc)
    hair_out = (pad + hair_src - yc_at) * sc
    chin_out = (pad + ys_at + chin - yc_at) * sc
    info = {"scale": round(sc, 4), "mouth_y": round(float(mouth_y), 1), "hair_y_min": round(float(hair_out.min()), 1),
            "hook_bottom": hook_bottom, "hair_clearance_min": round(float(hair_out.min()) - (hook_bottom or 0), 1),
            "chin_y_min": round(float(chin_out.min()), 1), "chin_y_max": round(float(chin_out.max()), 1),
            "crop_bottom_max": round(float(yc.max()) + h, 1), "source_bottom": pad + cam["src_h"],
            "plate_px_max": round(max(0.0, pad - float(yc.min())) * sc, 1), "crop_wh": [w, h], "col": [col_x0, col_w],
            "face_off_centre_px": round(float(np.max(np.abs(xs_c - (xl + w / 2)))) * sc, 1), "track_rows": int(len(r)),
            "chin_fallback": fallback}
    if arrays: return w, h, _yexpr(nodes, xl - col_x0), _yexpr(nodes, yc), col_x0, col_w, info, (nodes, xl, yc)
    return w, h, _yexpr(nodes, xl - col_x0), _yexpr(nodes, yc), col_x0, col_w, info


def plan_layer(ep, slug, layout, hook_bottom):
    """One camera layer: an input per (segment, camera shown in it), trimmed on that camera's own picture time for the
    segment start (sync evaluated PER SEGMENT from the drift model), anchored on the real nearest source frame,
    renumbered 1:1 at 25p right after the trim (VFR: fps=25 on its own branch first), framed from the face track,
    cut into the shot pieces and concatenated. Returns (fc_list, cmd, record, filter_path)."""
    S = ep.short(slug); fps = ep.fps
    m, T = ep.seg_map(slug)
    W, H = (ep.W, ep.H) if layout == "full" else (ep.W, ep.H // 2)
    pieces = TL.shot_pieces(m, S["shots"], fps)
    tracks = json.load(open(ep.p(ep.c["face_track"])))
    cache_p = ep.p(ep.c["seek_cache"]) if ep.c.get("seek_cache") else None
    cache = json.load(open(cache_p)) if cache_p and os.path.exists(cache_p) else {}
    margin = ep.c.get("hook_hair_margin", 40)
    inputs, fc, cat, seginfo, srcmap = [], [], [], [], []
    for i, (a0, a1, n, t0) in enumerate(m):
        dur = n / fps
        mine = [p for p in pieces if p[0] == i]
        for code in sorted(set(p[1] for p in mine)):
            cam = ep.cam(code); path = ep.p(cam["path"]); k = len(inputs)
            tc = ep.cam_time(code, a0)
            p0 = nearest_pts_packets(path, tc, cache)
            seek = max(0.0, round(p0 - 1.0, 3)); r0 = p0 - seek
            inputs.append(["-ss", f"{seek:.3f}", "-t", f"{r0 + dur + 1.0:.3f}", "-i", path])
            srcmap.append({"input": k, "seg": i, "cam": code, "audio_t0": round(a0, 4), "picture_t0": round(tc, 4),
                           "nearest_frame": round(p0, 4), "seek": seek, "anchor_error_ms": round((p0 - tc) * 1000, 1)})
            npc = sum(1 for p in mine if p[1] == code)
            w, h, xexpr, yexpr, cx0, cw, info = face_geometry(cam, tracks[code][slug], a0, dur, layout, W, H, hook_bottom,
                                                                margin, ep.c.get("chin_line"))
            if cam.get("vfr"):
                head = (f"[{k}:v]trim=start={r0 - 0.005:.4f}:end={r0 + dur + 0.3:.4f},setpts=PTS-STARTPTS,fps=25:round=near,"
                        f"settb=1/25,setpts=N,trim=end_frame={n}")
            else:
                head = f"[{k}:v]trim=start={r0 - 0.015:.4f}:end={r0 + dur + 0.2:.4f},settb=1/25,setpts=N,trim=end_frame={n}"
            pad = cam.get("pad_top", 0); lab = f"s{i}{code}"
            tail = (f"crop={w}:{h}:'{xexpr}':'{yexpr}',scale={W}:{H}:flags=lanczos,{cam.get('fx', 'null')},setsar=1,split={npc}"
                    + "".join(f"[{lab}_{j}]" for j in range(npc)))
            if pad:
                fc.append(f"{head},crop={cw}:{cam['src_h']}:{cx0}:0,split=2[{lab}a][{lab}b]")
                fc.append(f"[{lab}b]crop={cw}:{pad}:0:0,vflip,gblur=sigma=1:sigmaV=14[{lab}band]")
                fc.append(f"[{lab}band][{lab}a]vstack=shortest=1," + tail)
            else:
                fc.append(f"{head},crop={cw}:{cam['src_h']}:{cx0}:0," + tail)
            seginfo.append({"seg": i, "speaker": code, **info})
        used = {}
        for (_, code, lo, hi) in mine:
            j = used.get(code, 0); used[code] = j + 1
            lab = f"pc{len(cat)}"; cat.append(lab)
            fc.append(f"[s{i}{code}_{j}]trim=start_frame={lo}:end_frame={hi},setpts=PTS-STARTPTS[{lab}]")
    fc.append("".join(f"[{c}]" for c in cat) + f"concat=n={len(cat)}:v=1:a=0,settb=1/25,{ep.c['grade']},format=yuv420p[vout]")
    if cache_p: json.dump(cache, open(cache_p, "w"), indent=0)
    d = ep.altdir(slug); fpath = os.path.join(d, f"filter_base_{layout}.txt"); out = os.path.join(d, f"base_{layout}.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y"] + [x for q in inputs for x in q] + [
        "-filter_complex_script", fpath, "-map", "[vout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p", "-r", "25", "-fps_mode", "cfr",
        "-t", f"{T:.3f}", "-an", out]
    rec = {"slug": slug, "layout": layout, "adapter": "face4k", "duration": T, "frames": int(round(T * fps)), "inputs": srcmap,
           "seek": srcmap[0]["seek"], "shots": TL.shot_log(m, pieces, fps), "framing": seginfo}
    return fc, cmd, rec, fpath


# ------------------------------------------------------------------------------------------------ words
def words(ep, slug):
    """kept words of both people in output time (owner = the short's owner; OTHER = the other person, all of their
    words inside the kept segments, marked * when outside a reply window = their mic is closed there: never cut to
    them on those words, silent lips)"""
    S = ep.short(slug); m, T = ep.seg_map(slug)
    ow, ot, xw, xt = ep.mics(slug)
    own = [w for w in json.load(open(ot))["words"] if w.get("type", "word") == "word"]
    oth = [w for w in json.load(open(xt))["words"] if w.get("type", "word") == "word"]
    win = S.get("other_mic_windows", [])
    rows = [("OWNER", w, "") for w in own] + [("OTHER", w, "" if any(x[0] <= w["start"] <= x[1] for x in win) else "*") for w in oth]
    rows.sort(key=lambda r: r[1]["start"])
    print(f"[{slug}] owner={ep.owner(slug)} total {T:.2f}s")
    for who, w, flag in rows:
        for a0, a1, n, t0 in m:
            if a0 <= w["start"] < a1: print(f"{t0 + w['start'] - a0:6.2f}  {w['start']:8.2f}  {who:5s}{flag} {to_locale(w['text'])}")


# ------------------------------------------------------------------------------------------------ audio
BUS = ("aformat=sample_rates=48000:channel_layouts=mono,acompressor=threshold=0.063:ratio=2.5:attack=8:release=150:makeup=2,"
       "alimiter=limit=0.35:attack=3:release=60:level=false")


def _read(path, t0, dur):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.6f}", "-t", f"{dur:.6f}", "-i", path, "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def envelope(n, windows, t0, ramp=0.01, default_gain=1.0):
    """0 outside the windows, `gain` inside; linear ramps of exactly round(ramp*SR) samples placed OUTSIDE each window
    (opening from w0-ramp, closed again at w1+ramp)."""
    e = np.zeros(n); R = int(round(ramp * SR)); k = np.arange(n)
    for w in windows:
        g = w[2] if len(w) > 2 else default_gain
        a = int(round((w[0] - t0) * SR)); b = int(round((w[1] - t0) * SR))
        e = np.maximum(e, g * np.minimum(np.clip((k - (a - R)) / R, 0, 1), np.clip(((b + R) - k) / R, 0, 1)))
    return e


def _wav_f32(path, y):
    data = y.astype(np.float32).tobytes()
    hdr = (b"RIFF" + (36 + len(data)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") + (3).to_bytes(2, "little")
           + (1).to_bytes(2, "little") + SR.to_bytes(4, "little") + (SR * 4).to_bytes(4, "little") + (4).to_bytes(2, "little")
           + (32).to_bytes(2, "little") + b"data" + len(data).to_bytes(4, "little"))
    open(path, "wb").write(hdr + data)


def plan_audio(ep, slug, raw_out):
    """Writes the gated, cut, faded programme (sample-exact) to <edir>/audio_mix_pre.wav plus a gate audit
    (<edir>/audio_gates.json), and returns the bus command that turns it into raw_out; audio.run() loudnorms it."""
    S = ep.short(slug); fps = ep.fps; m, T = ep.seg_map(slug)
    ramp = ep.c["audio"].get("gate_ramp", 0.01)
    owner_wav, _, other_wav, _ = ep.mics(slug)
    seekA = m[0][0] - 2.0; span = m[-1][1] - seekA + 2.0
    own = _read(owner_wav, seekA, span); oth = _read(other_wav, seekA, span)
    n = min(len(own), len(oth)); own, oth = own[:n], oth[:n]
    win = S.get("other_mic_windows", [])
    mute = S.get("owner_mic_mute_windows", [w[:2] for w in win])
    g_oth = envelope(n, win, seekA, ramp, S.get("other_mic_gain", 1.0))
    g_own = 1.0 - envelope(n, mute, seekA, ramp, 1.0)
    mix = own * g_own + oth * g_oth
    k = len(m); parts = []
    audit = {"slug": slug, "owner": ep.owner(slug), "owner_wav": owner_wav, "other_wav": other_wav,
             "ramp_samples": int(round(ramp * SR)), "other_mic_open": win, "owner_mic_muted": mute, "segments": []}
    for i, (a0, a1, nf, t0) in enumerate(m):
        s0 = int(round((a0 - seekA) * SR)); L = nf * SR // fps
        x = mix[s0:s0 + L].copy()
        fin = 0.010 if i == 0 else 0.020
        fst = max(0.0, S["head_in"] - a0) if (i == 0 and "head_in" in S) else 0.0
        fout = 0.045 if i == k - 1 else 0.020
        z0, fi, fo = int(round(fst * SR)), int(round(fin * SR)), int(round(fout * SR))
        x[:z0] = 0; x[z0:z0 + fi] *= np.arange(fi) / fi; x[L - fo:] *= (fo - np.arange(fo)) / fo
        parts.append(x)
        audit["segments"].append({"mic_in": round(a0, 4), "mic_out": round(a0 + L / SR, 4), "out_t0": round(t0, 4), "samples": int(L)})
    y = np.concatenate(parts)
    pre = os.path.join(ep.edir(slug), "audio_mix_pre.wav"); _wav_f32(pre, y)
    audit.update({"total_samples": int(len(y)), "duration": round(len(y) / SR, 4), "timeline_T": round(T, 4)})
    json.dump(audit, open(os.path.join(ep.edir(slug), "audio_gates.json"), "w"), indent=1)
    return ["ffmpeg", "-v", "error", "-y", "-i", pre, "-af", BUS, "-c:a", "pcm_s24le", raw_out]
