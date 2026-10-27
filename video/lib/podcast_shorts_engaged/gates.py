"""Delivery gates.
Every gate is a hard fail. Pre-render gates (geometry, captions, gap) run on the plan; render gates run on the file.

Render gates: 1 timestamps (2160x3840, r = avg = 25/1, nb_frames == dur*25, every pts step 1/25, audio dur == video
dur) - 2 no duplicate-frame runs (full-res framemd5) - 3 clean decode - 4 sync (replay the layer's own trims with
showinfo: the source frame on output frame f must be the expected picture time within 20 ms) - 5 edges covered (no flat
band on the bottom edge of any frame or the top edge of camera-topped frames) - 6 caption band at the seam empty in
every animation split (rows >= 904 of the 1080x960 top panel at preview scale hold background only) - 7 size < 180 MB.

face4k (face4k-build, in-person multicam, sync_face4k replays EVERY (segment, camera) branch
head of the layer and maps every output frame to its source frame by checksum against the per-camera drift model;
anim_band reads the caption band on the rendered top track; caption_baseline_rows is the verify_v6 rendered-row check.
"""
import hashlib, json, os, re, subprocess
from fractions import Fraction
import numpy as np


def sh(c): return subprocess.run(c, capture_output=True, text=True)


def timestamps(path, W=2160, H=3840):
    js = json.loads(sh(["ffprobe", "-v", "error", "-show_streams", "-of", "json", path]).stdout)
    v = [s for s in js["streams"] if s["codec_type"] == "video"][0]; a = [s for s in js["streams"] if s["codec_type"] == "audio"][0]
    dur = float(v["duration"]); nb = int(v["nb_frames"])
    pts = sorted(int(x) for x in sh(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "packet=pts", "-of", "csv=p=0", path]).stdout.split())
    step = int(Fraction(1, 25) / Fraction(v["time_base"])); dd = sorted(set(int(x) for x in np.diff(pts)))
    rot = any("rotation" in json.dumps(s.get("side_data_list", "")) for s in js["streams"])
    rep = {"size": f'{v["width"]}x{v["height"]}', "r": v["r_frame_rate"], "avg": v["avg_frame_rate"], "nb_frames": nb, "expected": round(dur * 25),
           "duration": dur, "audio_duration": float(a["duration"]), "pts_steps": dd, "pts_step_expected": step, "rotation": rot}
    ok = (v["width"], v["height"]) == (W, H) and abs(nb - dur * 25) <= 1 and v["r_frame_rate"] == v["avg_frame_rate"] == "25/1" \
        and dd == [step] and abs(float(a["duration"]) - dur) < 0.05 and not rot
    return ok, rep


def dup_runs(path):
    hs = [l.split(",")[-1].strip() for l in sh(["ffmpeg", "-v", "error", "-i", path, "-map", "0:v", "-f", "framemd5", "-"]).stdout.splitlines()
          if l and not l.startswith("#")]
    runs, r, st = [], 1, 0
    for i in range(1, len(hs)):
        if hs[i] == hs[i - 1]: r += 1
        else:
            if r > 1: runs.append((round(st / 25, 2), r))
            r, st = 1, i
    if r > 1: runs.append((round(st / 25, 2), r))
    return not runs, runs


def decode_clean(path):
    e = sh(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"]).stderr.strip()
    return not e, e[:300]


def edges(path, top_frames=None, std_min=0.8):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "scale=540:960:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 960, 540).astype(float)
    top = fr[:, :4, :].reshape(len(fr), -1).std(axis=1); bot = fr[:, -4:, :].reshape(len(fr), -1).std(axis=1)
    bad_b = [i for i in range(len(fr)) if bot[i] < std_min]
    bad_t = [i for i in range(len(fr)) if top[i] < std_min and (top_frames is None or i in top_frames)]
    return not bad_b and not bad_t, {"uncovered_bottom_frames": len(bad_b), "uncovered_top_frames": len(bad_t),
                                     "first_bad_s": [round(i / 25, 2) for i in sorted(set(bad_b + bad_t))[:10]]}


def sync_mapping(mov, filter_txt, seek, m, av, times, fps=25):
    """authoritative sync proof: replay the camera layer's own per-segment trim with showinfo; downstream of the trim
    every stage is 1:1 (frame counts + no dup runs prove it)."""
    fl = open(filter_txt).read()
    trims = re.findall(r"\[v(\d+)\]trim=start=([0-9.]+):end=([0-9.]+)", fl)
    res = []
    for t in times:
        f = int(round(t * fps))
        for i, (a0, a1, n, t0) in enumerate(m):
            if int(round(t0 * fps)) <= f < int(round(t0 * fps)) + n: break
        fs = f - int(round(t0 * fps)); _, s0, s1 = next(x for x in trims if int(x[0]) == i)
        pr = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{seek:.4f}", "-t", "80", "-i", mov, "-map", "0:v", "-vf",
                             f"trim=start={s0}:end={s1},showinfo", "-frames:v", str(fs + 1), "-f", "null", "-"], capture_output=True)
        pts = [float(q) for q in re.findall(rb"pts_time:([\d.]+)", pr.stderr)]
        src = pts[fs] + seek; exp = a0 + av + fs / fps
        res.append({"t_out": round(f / fps, 2), "expected_src": round(exp, 3), "mapped_src": round(src, 3), "delta_ms": round((src - exp) * 1000, 1)})
    return all(abs(x["delta_ms"]) < 20 for x in res), res


def seam_band(preview_path, pcs, band=904, max_luma=45):
    """animation splits only: the top panel rows >= band (1080x960 preview scale) must hold background only, so the
    captions on the seam never sit on a graphic."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", preview_path, "-vf", f"scale=1080:1920,crop=1080:{960 - band}:0:{band},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 960 - band, 1080)
    bad = [(round(f / 25, 2), int(fr[f].max())) for a, b, k, sp in pcs if k == "S" and sp.get("top") == "anim"
           for f in range(a, min(b, len(fr))) if int(fr[f].max()) > max_luma]
    return not bad, bad[:12]


def audio_md5(path):
    return hashlib.md5(subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a", "-f", "s16le", "-"], capture_output=True).stdout).hexdigest()


def hook_hair(ep, base_full_rec, edl_pieces, hook_bottom):
    """geometry gate (pre-render): in every full-frame segment the highest hair row stays >= hook bottom + 40 (un-punched)
    and, inside every punch-in, >= max(570, hook bottom + 20)."""
    m_un = ep.c.get("hook_hair_margin", 40); m_p = ep.c.get("hook_punch_margin", 20)
    clear_p = max(ep.c.get("hook_clear_y", 570), hook_bottom + m_p)
    out, ok = [], True
    for x in base_full_rec["framing"]:
        hair = x["hair_y_min"]; good = hair >= hook_bottom + m_un - 3      # 3 px: even-pixel crop rounding
        for p in edl_pieces:
            if p.get("z", 1.0) != 1.0 and p.get("speaker") == x["speaker"]:
                pv = p["pivot_y"]; hp = pv - (pv - hair) * p["z"]
                good &= hp >= clear_p - 3
        ok &= good; out.append({"seg": x["seg"], "speaker": x["speaker"], "hair_y_min": hair, "ok": good})
    return ok, out


# ------------------------------------------------------------------------------------------------ face4k (face4k-build) render gates
def _layer_inputs(cmd):
    """the -ss/-t/-i groups of a camera-layer command, in input order"""
    out, cur = [], []
    i = 0
    while i < len(cmd):
        if cmd[i] in ("-ss", "-t"): cur += [cmd[i], cmd[i + 1]]; i += 2; continue
        if cmd[i] == "-i": out.append(cur + ["-i", cmd[i + 1]]); cur = []; i += 2; continue
        i += 1
    return out


def _layer_heads(filter_txt):
    """{input index: (first trim, rest of the head up to and incl. trim=end_frame=N, N)} from a face4k layer graph"""
    heads = {}
    for mm in re.finditer(r"\[(\d+):v\](trim=start=[0-9.]+:end=[0-9.]+),(.*?trim=end_frame=(\d+))", open(filter_txt).read()):
        heads[int(mm[1])] = (mm[2], mm[3], int(mm[4]))
    return heads


def sync_face4k(ep, slug, layout="full", tol_ms=20.0, vfr_slack_ms=0.5):
    """Sync gate for the face4k (in-person multicam, per-camera drift model) layer, ported from sync_mapping.
    Every input of the layer is one (segment, camera) branch; for EACH branch the layer's own head chain (seek, trim,
    VFR fps=25 resample, 1:1 renumber, end_frame) is replayed with showinfo before and after it, and every output frame
    is mapped back to its source frame by its plane checksum. Each output frame j of segment i on camera c must show
    the source frame at the camera's picture time cam_time(c, a0 + j/25) within tol_ms (the drift model, evaluated per
    frame). Also reports repeated / skipped source frames inside a branch (VFR resample). Downstream of the head every
    stage is 1:1 (frame counts + dup-run gate)."""
    d = ep.altdir(slug); fps = ep.fps
    rec = json.load(open(os.path.join(d, f"base_{layout}.json")))
    cmd = json.load(open(os.path.join(d, f"filter_base_{layout}.cmd.json")))
    heads = _layer_heads(os.path.join(d, f"filter_base_{layout}.txt")); groups = _layer_inputs(cmd)
    m, T = ep.seg_map(slug); res, ok = [], True
    for inp in rec["inputs"]:
        k, i, code = inp["input"], inp["seg"], inp["cam"]
        a0, _, n, t0 = m[i]
        trim, rest, nend = heads[k]
        seek = float(groups[k][groups[k].index("-ss") + 1])
        for attempt in range(3):     # log lines from ffmpeg's threads can interleave under load: re-run a branch that
            pr = subprocess.run(["ffmpeg", "-v", "info", "-nostdin"] + groups[k] + ["-map", "0:v", "-vf", f"{trim},showinfo,{rest},showinfo",
                                "-f", "null", "-"], capture_output=True)       # parsed short or with an unknown checksum
            src, outc = [], []
            for ln in pr.stderr.decode("utf-8", "replace").splitlines():
                mm = re.search(r"Parsed_showinfo_(\d+).*?pts_time:\s*([-\d.e]+).*?checksum:([0-9A-Fa-f]+)", ln)
                if mm: (src if int(mm[1]) == 1 else outc).append((float(mm[2]), mm[3]))
            if len(outc) == n and {c for _, c in outc} <= {c for _, c in src}: break
        # the shifted showinfo pts are quantised to the stream time base (1/600 on the iPhone = 1.7 ms): snap every mapped
        # time to the file's real packet pts so the delta is the true picture error
        tdur = float(groups[k][groups[k].index("-t") + 1])
        real = np.array(sorted(float(x.strip(",")) for x in subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v", "-read_intervals", f"{max(seek - 1, 0):.3f}%{seek + tdur + 1:.3f}",
             "-show_entries", "packet=pts_time", "-of", "csv=p=0", groups[k][-1]], capture_output=True, text=True).stdout.split()
            if x.strip(",") not in ("", "N/A")))
        snap = lambda q: float(real[np.argmin(np.abs(real - q))]) if len(real) else q
        bycs = {}
        for p, cs in src: bycs.setdefault(cs, []).append(snap(p + seek))
        deltas, used, missing, not_nearest = [], [], 0, 0
        for j, (_, cs) in enumerate(outc):
            exp = ep.cam_time(code, a0 + j / fps)
            cands = bycs.get(cs)
            if not cands: missing += 1; continue
            s = min(cands, key=lambda q: abs(q - exp)); used.append(s); deltas.append((s - exp) * 1000)
            # informational: frames over tol_ms that are not the nearest real frame (the 1:1 VFR resample keeps the anchor's
            # phase; switching phase mid-branch would duplicate a frame, which is worse - tried and rejected
            if abs(s - exp) * 1000 >= tol_ms and abs(snap(exp) - s) > 1e-6: not_nearest += 1
        reps = len(used) - len(set(used))
        steps = np.diff(sorted(set(used))) if len(set(used)) > 1 else np.array([0.04])
        skips = int(np.sum(steps > 1.5 / fps))
        mx = float(np.max(np.abs(deltas))) if deltas else 1e9
        # gate: every frame mapped, no source frame shown twice, |delta| <= tol_ms + vfr_slack_ms (the iPhone clock ticks in
        # 1/600 s, so a nearest-frame anchor can walk a fraction of a tick past half a frame inside a branch)
        # VFR cameras: the iPhone clock runs in 1/600 s ticks, so across a branch the nearest-frame phase can drift by one
        # tick (1.7 ms) past half a frame with NO nearer frame on the other side (checked on face4k-build referrals / vitamin:
        # either anchor lands 20.5-21.2 ms at one end) - the floor for 1:1 VFR->25p without frame blending
        slack = vfr_slack_ms if not ep.cam(code).get("vfr") else max(vfr_slack_ms, 1.7)
        good = len(outc) == n == nend and not missing and reps == 0 and mx <= tol_ms + slack
        ok &= good
        res.append({"input": k, "seg": i, "cam": code, "frames": len(outc), "expected_frames": n, "unmatched": missing,
                    "delta_ms_min": round(min(deltas), 1) if deltas else None, "delta_ms_max": round(max(deltas), 1) if deltas else None,
                    "max_abs_ms": round(mx, 1), "over_tol_not_nearest": not_nearest, "repeated_src_frames": reps, "skipped_src_frames": skips, "ok": good})
    return ok, res


def same_heads(ep, slug):
    """the panel layer replays exactly the same per-branch head chains as the full layer (so one sync replay covers both)"""
    d = ep.altdir(slug)
    a = _layer_heads(os.path.join(d, "filter_base_full.txt")); b = _layer_heads(os.path.join(d, "filter_base_panel.txt"))
    ca = _layer_inputs(json.load(open(os.path.join(d, "filter_base_full.cmd.json"))))
    cb = _layer_inputs(json.load(open(os.path.join(d, "filter_base_panel.cmd.json"))))
    return a == b and ca == cb


def anim_band(top_anim, pcs, band_px=1808, max_luma=45):
    """caption band (band_audit.py port, read on the rendered 2160x1920 top track): inside every animation split, rows
    >= band_px (= 904 on the 1080x960 comp) hold background only."""
    H = 1920 - band_px
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", top_anim, "-vf", f"crop=2160:{H}:0:{band_px},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, H, 2160)
    bad = [(round(f / 25, 2), int(fr[f].max())) for a, b, k, sp in pcs if k == "S" and sp.get("top") == "anim"
           for f in range(a, min(b, len(fr))) if int(fr[f].max()) > max_luma]
    return not bad, {"frames": len(fr), "violations": len(bad), "first": bad[:12],
                     "band_max_luma": int(max((int(fr[f].max()) for a, b, k, sp in pcs if k == "S" and sp.get("top") == "anim"
                                               for f in range(a, min(b, len(fr)))), default=0))}


def caption_baseline_rows(path, samples, y0=1800, hgt=260):
    """rendered caption baseline (verify_v6 caption_rows port): per sample, the uppermost strong peak of glyph-bottom
    rows of white / muted blue-grey caption ink in rows y0..y0+hgt. Informational (bright picture can add ink)."""
    rows = {}
    for lab, t in samples:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", f"crop=2160:{hgt}:0:{y0}",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        im = np.frombuffer(r, np.uint8).reshape(hgt, 2160, 3).astype(int)
        mn = im.min(axis=2); mx = im.max(axis=2); wht = (mn > 165) & (mx - mn < 45)
        wht |= (im[..., 0] > 200) & (im[..., 0] - im[..., 1] > 90)      # accent emphasis ink too
        xs = np.where(wht.any(axis=0))[0]
        if not len(xs): rows[f"{lab}@{t}"] = None; continue
        bots = np.array([int(np.where(wht[:, x])[0].max()) for x in xs]); bots = bots[bots < hgt - 12]   # picture at the crop edge
        if not len(bots): rows[f"{lab}@{t}"] = None; continue
        v, c = np.unique(bots, return_counts=True)
        # the MODAL glyph-bottom row (flat bottoms dominate; the reference-build "uppermost strong peak" rule picked the f/t crossbars)
        rows[f"{lab}@{t}"] = int(v[c.argmax()]) + y0
    return rows
