"""Podcast episode - build the multicam + silence/filler-cut EDL.

Reads the diarized transcript + runs silencedetect, decides which camera shows when
(close-up of the active speaker, two-shot breathers + banter coverage), and removes
silences + light fillers. Every boundary is quantised to the frame grid so video
(frames) and audio (samples; 48000/25 = 1920 exactly) stay locked with zero drift.

Usage:
  python build_edl.py --episode-dir <eX folder> --edit-dir <work dir> [--host speaker_0]

Requires <edit-dir>/transcripts/full-audio.json (run transcribe.py first).
Writes <edit-dir>/edl.json and prints stats (including the host/guest mapping it chose).
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument("--episode-dir", required=True, type=Path)
ap.add_argument("--edit-dir", required=True, type=Path)
ap.add_argument("--host", default=None, help="force host speaker id (e.g. speaker_0); default auto")
ap.add_argument("--fps", type=float, default=25.0)  # house standard 25fps; must match camera fps
ap.add_argument("--extra-cut", nargs=2, type=float, action="append", metavar=("START", "END"),
                help="extra removal range(s) in ORIGINAL source seconds; repeatable")
A = ap.parse_args()

EP, ED, FPS = A.episode_dir.resolve(), A.edit_dir.resolve(), A.fps
SRC = {"host": "host-shot-4k.mov", "guest": "guest-shot-4k.mov", "double": "double-shot-4k.mov"}
FULL_AUDIO = EP / "full-audio.wav"

# --- multicam tuning ---
MERGE_SHORT_TURN, DOUBLE_TARGET, DOUBLE_MIN_GAP = 1.8, 17.0, 8.0
DOUBLE_MAX_LEN, BRIDGE_MIN_TURN, MIN_SHOT, OTHER_MAX = 5.0, 10.0, 1.5, 2.5
# --- cut tuning ---
PAD, SIL_MIN_REMOVE, REMOVAL_MERGE_GAP, MIN_KEEP = 0.10, 0.08, 0.20, 0.10
FILLERS = {"um", "uh", "er", "erm", "uhm", "umm", "uhh"}
SIL_NOISE_DB, SIL_MIN_DUR = "-30dB", 0.4
MINF = 12  # min displayed-shot length in frames (0.4s) -> no 1-3 frame flashes

def F(t): return int(round(t * FPS))
def norm(t): return re.sub(r"[^\w]", "", t).lower()

# ---------------------------------------------------------------- load transcript
tj = json.loads((ED / "transcripts" / "full-audio.json").read_text())
DUR = float(tj["audio_duration_secs"])
words = [w for w in tj["words"] if w.get("type") == "word"]

# ---------------------------------------------------------------- host/guest mapping
wsec = Counter()
for w in words:
    wsec[w["speaker_id"]] += w["end"] - w["start"]
spk_ids = sorted(wsec, key=lambda s: -wsec[s])
if A.host:
    host_id = A.host
else:
    # heuristic: the host (interviewer) speaks LESS than the guest
    host_id = min(wsec, key=lambda s: wsec[s])
guest_id = [s for s in spk_ids if s != host_id][0]
SPK = {host_id: "host", guest_id: "guest"}

# ---------------------------------------------------------------- silencedetect (cached)
sd_log = ED / "silencedetect.log"
if not sd_log.exists():
    subprocess.run(["ffmpeg", "-hide_banner", "-i", str(FULL_AUDIO),
                    "-af", f"silencedetect=noise={SIL_NOISE_DB}:d={SIL_MIN_DUR}", "-f", "null", "-"],
                   stderr=open(sd_log, "w"), check=True)

# ---------------------------------------------------------------- turns
raw = []
for w in words:
    spk = SPK[w["speaker_id"]]
    if raw and raw[-1]["spk"] == spk:
        raw[-1]["end"] = w["end"]
    else:
        raw.append({"spk": spk, "start": w["start"], "end": w["end"]})

def coalesce(ts):
    out = []
    for t in ts:
        if out and out[-1]["spk"] == t["spk"]:
            out[-1]["end"] = max(out[-1]["end"], t["end"])
        else:
            out.append(dict(t))
    return out

turns = coalesce(raw)
while len(turns) > 1:
    cand = [i for i, t in enumerate(turns) if (t["end"] - t["start"]) < MERGE_SHORT_TURN]
    if not cand:
        break
    i = min(cand, key=lambda i: turns[i]["end"] - turns[i]["start"])
    if i == 0:
        tgt = 1
    elif i == len(turns) - 1:
        tgt = i - 1
    else:
        a, b = turns[i - 1], turns[i + 1]
        tgt = i - 1 if (a["end"] - a["start"]) >= (b["end"] - b["start"]) else i + 1
    turns[i]["spk"] = turns[tgt]["spk"]
    turns = coalesce(turns)

turns[0]["start"] = 0.0
for i in range(len(turns) - 1):
    turns[i]["end"] = turns[i + 1]["start"]
turns[-1]["end"] = DUR

# ---------------------------------------------------------------- sentence boundaries -> atoms
sent_bounds = sorted({w["end"] for w in words
                      if w["text"].strip().rstrip('"\'”’').endswith((".", "?", "!"))})
def internal(a, b): return [t for t in sent_bounds if a + 0.4 < t < b - 0.4]
atoms = []
for tn in turns:
    pts = [tn["start"]] + internal(tn["start"], tn["end"]) + [tn["end"]]
    for j in range(len(pts) - 1):
        atoms.append({"spk": tn["spk"], "start": pts[j], "end": pts[j + 1], "turn_dur": tn["end"] - tn["start"]})

# ---------------------------------------------------------------- shot timeline
shots = []
def emit(src, a, b):
    if b - a <= 1e-6: return
    if shots and shots[-1][0] == src and abs(shots[-1][2] - a) < 1e-6:
        shots[-1] = (src, shots[-1][1], b)
    else:
        shots.append((src, a, b))

accum, prev = 0.0, None
for idx, at in enumerate(atoms):
    spk, a, b, tdur = at["spk"], at["start"], at["end"], at["turn_dur"]
    if prev is not None and spk != prev:
        accum = 0.0
    cu, dur = SRC[spk], b - a
    is_last = (idx + 1 >= len(atoms)) or (atoms[idx + 1]["spk"] != spk)
    want = (accum >= DOUBLE_TARGET) or (is_last and tdur >= BRIDGE_MIN_TURN and accum >= DOUBLE_MIN_GAP)
    if want:
        if dur <= DOUBLE_MAX_LEN + 1.0:
            emit(SRC["double"], a, b); accum = 0.0
        else:
            emit(SRC["double"], a, a + DOUBLE_MAX_LEN); emit(cu, a + DOUBLE_MAX_LEN, b)
            accum = b - (a + DOUBLE_MAX_LEN)
    else:
        emit(cu, a, b); accum += dur
    prev = spk

# overlap pass: a close-up holding too much of the OTHER speaker -> two-shot
wspans = [(SPK[w["speaker_id"]], w["start"], w["end"]) for w in words]
def other_talk(a, b, spk):
    return sum(max(0.0, min(b, we) - max(a, ws)) for s, ws, we in wspans if s != spk)
fixed = []
for src, a, b in shots:
    if src in (SRC["host"], SRC["guest"]):
        spk = "host" if src == SRC["host"] else "guest"
        ot = other_talk(a, b, spk)
        if ot > OTHER_MAX or (b - a >= 2.0 and ot >= 1.2 and ot > 0.40 * (b - a)):
            src = SRC["double"]
    fixed.append((src, a, b))
shots = []
for s in fixed:
    if shots and shots[-1][0] == s[0] and abs(shots[-1][2] - s[1]) < 1e-6:
        shots[-1] = (s[0], shots[-1][1], s[2])
    else:
        shots.append(s)
# enforce MIN_SHOT
merged = []
for s in shots:
    if merged and (s[2] - s[1]) < MIN_SHOT:
        merged[-1] = (merged[-1][0], merged[-1][1], s[2])
    elif merged and merged[-1][0] == s[0]:
        merged[-1] = (merged[-1][0], merged[-1][1], s[2])
    else:
        merged.append(s)
shots = merged

# ---------------------------------------------------------------- removals -> keeps
log = sd_log.read_text()
sil = re.findall(r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", log, re.S)
removals = []
for s, e in sil:
    rs, re_ = float(s) + PAD, float(e) - PAD
    if re_ - rs > SIL_MIN_REMOVE:
        removals.append([rs, re_])
n_fill = 0
for w in words:
    if norm(w["text"]) in FILLERS:
        removals.append([w["start"], w["end"]]); n_fill += 1
n_extra = 0
for s, e in (A.extra_cut or []):
    removals.append([float(s), float(e)]); n_extra += 1
removals.sort()
mrm = []
for r in removals:
    if mrm and r[0] <= mrm[-1][1] + REMOVAL_MERGE_GAP:
        mrm[-1][1] = max(mrm[-1][1], r[1])
    else:
        mrm.append(r[:])
keeps, cur = [], 0.0
for rs, re_ in mrm:
    rs, re_ = max(0.0, min(rs, DUR)), max(0.0, min(re_, DUR))
    if rs - cur >= MIN_KEEP:
        keeps.append([cur, rs])
    cur = max(cur, re_)
if DUR - cur >= MIN_KEEP:
    keeps.append([cur, DUR])

# ---------------------------------------------------------------- unified EDL (frames)
vid, si = [], 0
for ka, kb in keeps:
    kaf, kbf = F(ka), F(kb)
    while si < len(shots) and F(shots[si][2]) <= kaf:
        si += 1
    j = si
    while j < len(shots) and F(shots[j][1]) < kbf:
        src, ss, se = shots[j]
        a, b = max(kaf, F(ss)), min(kbf, F(se))
        if b - a >= 1:
            if vid and vid[-1]["src"] == src and vid[-1]["b"] == a:
                vid[-1]["b"] = b
            else:
                vid.append({"src": src, "a": a, "b": b})
        j += 1
clean = []
for p in vid:
    if clean and (p["b"] - p["a"]) < MINF:
        pr = clean[-1]
        if pr["b"] == p["a"]:
            pr["b"] = p["b"]
        else:
            clean.append({"src": pr["src"], "a": p["a"], "b": p["b"]})
    else:
        clean.append(dict(p))
co = []
for p in clean:
    if co and co[-1]["src"] == p["src"] and co[-1]["b"] == p["a"]:
        co[-1]["b"] = p["b"]
    else:
        co.append(dict(p))
vid = co
ak = []
for p in vid:
    if ak and ak[-1][1] == p["a"]:
        ak[-1][1] = p["b"]
    else:
        ak.append([p["a"], p["b"]])

video_edl = [{"src": p["src"], "in_f": p["a"], "out_f": p["b"], "in": p["a"]/FPS, "out": p["b"]/FPS} for p in vid]
audio_keeps = [{"in_f": a, "out_f": b, "in": a/FPS, "out": b/FPS} for a, b in ak]
vf = sum(p["out_f"] - p["in_f"] for p in video_edl)
af = sum(k["out_f"] - k["in_f"] for k in audio_keeps)
src_secs = Counter()
for p in video_edl:
    src_secs[p["src"]] += (p["out_f"] - p["in_f"]) / FPS

def opening(spk_id, n=3):
    out = []
    for w in words:
        if w["speaker_id"] == spk_id:
            out.append(w["text"])
        if len(out) >= 12:
            break
    return " ".join(out)

stats = {
    "host_speaker": host_id, "guest_speaker": guest_id,
    "host_words_sec": round(wsec[host_id], 1), "guest_words_sec": round(wsec[guest_id], 1),
    "host_opening": opening(host_id), "guest_opening": opening(guest_id),
    "orig_duration": round(DUR, 2), "final_duration": round(vf / FPS, 2),
    "removed": round(DUR - vf / FPS, 2), "video_segments": len(video_edl),
    "fillers_removed": n_fill, "silences_removed": len(mrm), "extra_cuts": n_extra,
    "av_lock_ok": vf == af, "min_segment_frames": min(p["out_f"] - p["in_f"] for p in video_edl),
    "src_minutes": {k: round(v / 60, 2) for k, v in src_secs.items()},
}
(ED / "edl.json").write_text(json.dumps(
    {"fps": FPS, "duration": DUR, "episode_dir": str(EP), "src_files": SRC,
     "video_edl": video_edl, "audio_keeps": audio_keeps, "stats": stats}, indent=2))
print(json.dumps(stats, indent=2))
