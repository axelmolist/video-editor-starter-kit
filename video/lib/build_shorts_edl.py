#!/usr/bin/env python3
"""
build_shorts_edl.py - draft a punchy, silence-free EDL for a raw talking-head short.

The shorts-editor agent uses this to turn a raw clip into a cut plan. It detects
REAL silence from the audio (never from the transcript - Scribe inflates word.end
to hide pauses), keeps whole sentences, and removes only genuine dead air.

What it does:
  1. ffprobe the source for duration.
  2. silencedetect (default noise=-35dB, min d=0.5s) -> the genuine dead-air gaps.
  3. Speech runs = the complement. Each run keeps its natural <0.5s internal pauses
     (so sentences stay whole and never sound chopped).
  4. Pad each run: start -= lead (0.05s), end += tail (0.15s). That leaves at most
     ~0.20s at any join and never clips the end of a word.
  5. If a transcript JSON is given, label each run with the words it overlaps (quote)
     so the agent can SEE what each segment says and prune flubs/false starts/repeats.
  6. Emit an EDL with grade:"" (NO colour grade - the creator ships these raw).

The agent then deletes the ranges it does not want (false starts, flubbed takes,
repeated weaker takes, filler) and renders with helpers/render.py. It must NOT add a
grade.

Usage:
  build_shorts_edl.py <source.mov> --out edit/<slug>.edl.json \
      [--transcript edit/transcripts/<name>.json] \
      [--noise -35dB] [--min-silence 0.5] [--lead 0.05] [--tail 0.15]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def detect_silences(path: str, noise: str, min_silence: float):
    """Return list of (start, end) silence intervals from ffmpeg silencedetect."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
         "-af", f"silencedetect=noise={noise}:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    log = proc.stderr
    starts = [float(m) for m in re.findall(r"silence_start:\s*([0-9.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([0-9.]+)", log)]
    # silencedetect emits start then end in order; zip defensively
    sils = []
    si = ei = 0
    # If the clip starts in silence, the first event is a silence_start: 0
    while si < len(starts):
        s = starts[si]
        e = ends[ei] if ei < len(ends) else None
        if e is None or e < s:
            ei += 1
            continue
        sils.append((s, e))
        si += 1
        ei += 1
    return sils


def speech_runs(duration: float, sils):
    """Complement of the silence intervals across [0, duration]."""
    runs = []
    cursor = 0.0
    for s, e in sils:
        if s > cursor + 1e-3:
            runs.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration - 1e-3:
        runs.append((cursor, duration))
    # drop sub-100ms slivers (not real speech)
    return [(a, b) for a, b in runs if (b - a) > 0.10]


def load_words(transcript_path: str):
    if not transcript_path:
        return None
    d = json.load(open(transcript_path))
    # keep word + spacing tokens so the rebuilt quote reads naturally
    words = [w for w in d.get("words", []) if w.get("type") in ("word", "spacing")]
    try:     # British spelling in the quotes - Scribe writes American
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from spelling import normalise_words
        words = normalise_words(words)
    except ImportError:
        pass
    return words


def quote_for(run, words):
    if not words:
        return ""
    a, b = run
    toks = [w["text"] for w in words if w["end"] > a and w["start"] < b]
    return "".join(toks).strip()


def main(argv=None):
    p = argparse.ArgumentParser(description="Draft a silence-free EDL for a raw short (no grade).")
    p.add_argument("source")
    p.add_argument("--out", required=True, help="EDL JSON output path")
    p.add_argument("--transcript", default=None, help="cached Scribe JSON to label segments")
    p.add_argument("--noise", default="-35dB", help="silencedetect noise floor (default -35dB)")
    p.add_argument("--min-silence", type=float, default=0.5, help="min dead-air to cut, seconds (default 0.5)")
    p.add_argument("--lead", type=float, default=0.05, help="pad before each run start, seconds")
    p.add_argument("--tail", type=float, default=0.15, help="pad after each run end, seconds")
    args = p.parse_args(argv)

    src = str(Path(args.source).resolve())
    name = Path(src).stem
    dur = ffprobe_duration(src)
    sils = detect_silences(src, args.noise, args.min_silence)
    runs = speech_runs(dur, sils)
    words = load_words(args.transcript)

    ranges = []
    for a, b in runs:
        start = round(max(0.0, a - args.lead), 3)
        end = round(min(dur, b + args.tail), 3)
        ranges.append({"source": name, "start": start, "end": end,
                       "quote": quote_for((a, b), words)})

    edl = {
        "version": 1,
        "sources": {name: src},
        "grade": "",
        "_note": f"Audio-true cut: silencedetect {args.noise}/d={args.min_silence}s, "
                 f"pad {args.lead} lead / {args.tail} tail. NO grade (ship raw). "
                 f"PRUNE flubs/false starts/repeated takes before rendering.",
        "ranges": ranges,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(edl, open(args.out, "w"), indent=2)

    print(f"source: {name}  duration {dur:.2f}s")
    print(f"{len(sils)} dead-air gaps >= {args.min_silence}s  ->  {len(ranges)} speech segments")
    print(f"wrote draft EDL: {args.out}\n")
    for i, r in enumerate(ranges):
        print(f"  [{i:2d}] {r['start']:7.2f}-{r['end']:7.2f}  {r['quote']!r}")
    print("\nNext: delete the segments you don't want (false starts, flubs, repeated weaker "
          "takes, filler), keep grade \"\", then render with helpers/render.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
