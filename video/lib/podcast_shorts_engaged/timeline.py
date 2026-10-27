"""Timeline maths shared by every stage. Pure functions, no I/O."""


def snap(segs, fps, v_start, av):
    """Snap each (a0, a1) host-audio segment so its picture in/out land on the host camera's frame grid
    (picture = audio + av; grid = v_start + k/fps). Returns [(a0, a1, n_frames)]."""
    out = []
    for a0, a1 in segs:
        v0 = v_start + round((a0 + av - v_start) * fps) / fps
        n = round((a1 - a0) * fps)
        out.append((v0 - av, v0 - av + n / fps, n))
    return out


def seg_map(segs, fps, v_start, av):
    """[(a0, a1, n_frames, out_t0)], total seconds"""
    m, T = [], 0.0
    for a0, a1, n in snap(segs, fps, v_start, av):
        m.append((a0, a1, n, T)); T += n / fps
    return m, T


def to_out(m, a):
    """host-audio time -> output seconds (None if outside every segment, 80 ms tolerance)"""
    for a0, a1, n, t0 in m:
        if a0 - 0.08 <= a <= a1 + 0.08:
            return t0 + min(max(a, a0), a1) - a0
    return None


def frames(t, fps=25): return int(round(t * fps))


def shot_pieces(m, shots, fps=25):
    """Split the segment map by the shot list [(out_t, cam_code)] -> [(seg_index, cam, lo_frame, hi_frame)]
    (frame indices relative to the segment start)."""
    TF = sum(n for _, _, n, _ in m)
    marks = [(frames(t, fps), w) for t, w in shots]
    bounds = [(marks[j][0], marks[j + 1][0] if j + 1 < len(marks) else TF, marks[j][1]) for j in range(len(marks))]
    pieces = []
    for i, (a0, a1, n, t0) in enumerate(m):
        f0 = frames(t0, fps); f1 = f0 + n
        for lo, hi, s in bounds:
            l2, h2 = max(f0, lo), min(f1, hi)
            if h2 > l2: pieces.append((i, s, l2 - f0, h2 - f0))
    return pieces


def shot_log(m, pieces, fps=25):
    """the base_full.json "shots" list: who is on camera, in output seconds"""
    return [{"seg": i, "shot": s, "out_start": round((frames(m[i][3], fps) + lo) / fps, 2),
             "out_end": round((frames(m[i][3], fps) + hi) / fps, 2)} for i, s, lo, hi in pieces]


def state_pieces(states, T, fps=25):
    """engagement states [(t, kind, spec)] -> [(a_frame, b_frame, kind, spec)], total frames"""
    TF = frames(T, fps)
    out = []
    for j, (t, k, sp) in enumerate(states):
        a = frames(t, fps); b = frames(states[j + 1][0], fps) if j + 1 < len(states) else TF
        out.append((a, b, k, sp))
    return out, TF


def state_at(pcs, t, fps=25):
    f = frames(t, fps)
    for a, b, k, sp in pcs:
        if a <= f < b: return k
    return pcs[-1][2]


def change_log(pcs, base_shots, steps, T, fps=25, eff_z=None):
    """Every moment something visibly changes: state changes (consecutive animation splits merge, the animation's own
    steps carry them), camera/shot changes, and the animation steps. Returns (changes, gaps, max_gap) where a gap is
    (seconds, from, to). Gate: max gap <= 2.0 s; reference-build medians were 0.5-0.65 s. eff_z = the punch-in actually applied per
    piece (a requested punch-in the hook rule had to drop is not a visible change)."""
    shot_changes = sorted(set(s["out_start"] for s in base_shots))
    ez = eff_z or [None] * len(pcs)
    vis = [round(a / fps, 2) for j, (a, b, k, sp) in enumerate(pcs)
           if not (j > 0 and k == "S" and pcs[j - 1][2] == "S" and sp.get("top") == "anim" and pcs[j - 1][3].get("top") == "anim")
           and not (j > 0 and k == "F" and pcs[j - 1][2] == "F" and ez[j] is not None and ez[j] == ez[j - 1])]   # a dropped punch-in is no change
    changes = sorted(set(vis + shot_changes + list(steps) + [0.0]))
    gaps = [(round(changes[i + 1] - changes[i], 2), changes[i], changes[i + 1]) for i in range(len(changes) - 1)] \
        + [(round(T - changes[-1], 2), changes[-1], T)]
    return changes, gaps, max(gaps)
