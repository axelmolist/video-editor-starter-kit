"""Podcast episode - list every hook word with its HOOK-LOCAL timestamp.

Makes caption re-timing trivial: it maps each spoken word inside the chosen hook clips
to its time in the assembled hook (cumulative across clips/sub-ranges, frame-quantised
exactly like build_hook.py). Pick the peak words + read their times straight into CAPS
in gen_hook_captions.py.

  python hook_words.py --edit-dir <work> --hook <hook.json>
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--edit-dir", required=True, type=Path)
ap.add_argument("--hook", required=True, type=Path)
ap.add_argument("--fps", type=float, default=25.0)  # house standard 25fps; must match camera fps
A = ap.parse_args()
FPS = A.fps
def F(t): return int(round(t * FPS))

tj = json.loads((A.edit_dir / "transcripts" / "full-audio.json").read_text())
words = [w for w in tj["words"] if w.get("type") == "word"]
clips = json.loads(A.hook.read_text())["clips"]
ranges = [(F(a), F(b)) for clip in clips for (a, b) in clip]  # flattened, in order

cum = 0  # frames elapsed in the hook
print("hook_t   orig_t   text")
for (a, b) in ranges:
    for w in words:
        if a / FPS - 0.01 <= w["start"] < b / FPS:
            ht = cum / FPS + (w["start"] - a / FPS)
            print(f"{ht:6.2f}  {w['start']:7.2f}  {w['text']}")
    cum += (b - a)
    print(f"--- clip boundary @ hook {cum/FPS:.2f}s ---")
