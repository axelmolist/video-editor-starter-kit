#!/usr/bin/env python3
"""Ingest audio check: flag clips whose audio track is dead (noise floor only).

Born after a week of vlog e3 footage came back silent: the Sony
ECM-B10 shoe mic had flipped from AUTO to MANUAL with the level dial at zero.
Every clip still HAD an audio stream, so ffprobe looked fine - only the levels
gave it away (peak ~-70 dBFS, RMS ~-85 dBFS, flat). Run this on every card
before editing, or straight after a shoot.

Usage:
    python video/lib/audio_check.py <dir-or-files...> [--threshold -40] [--move <subdir>]

Exit code 1 if any clip is dead. --move relocates dead clips into <subdir>
under their own folder (e.g. --move silent).
"""
import argparse, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXT = {".mp4", ".mov", ".mxf", ".m4v"}


def peak_db(path):
    cmd = ["ffmpeg", "-v", "info", "-i", str(path), "-vn",
           "-af", "astats=measure_overall=Peak_level:measure_perchannel=0", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True).stderr
    m = re.findall(r"Peak level dB:\s*(-?[\d.]+|-inf)", out)
    if not m:
        return None  # no audio stream at all
    v = m[-1]
    return float("-inf") if v == "-inf" else float(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--threshold", type=float, default=-40.0, help="peak dBFS below this = dead")
    ap.add_argument("--move", default="", help="move dead clips into this subfolder")
    a = ap.parse_args()
    files = []
    for p in a.paths:
        p = Path(p)
        files += sorted(x for x in p.rglob("*") if x.suffix.lower() in EXT) if p.is_dir() else [p]
    with ThreadPoolExecutor(6) as ex:
        peaks = list(ex.map(peak_db, files))
    dead = []
    for f, pk in zip(files, peaks):
        if pk is None:
            status = "NO AUDIO STREAM"; dead.append(f)
        elif pk < a.threshold:
            status = f"DEAD  peak {pk:7.1f} dBFS"; dead.append(f)
        else:
            status = f"ok    peak {pk:7.1f} dBFS"
        print(f"{status}  {f}")
    print(f"\n{len(dead)} dead / {len(files)} clips")
    if a.move and dead:
        for f in dead:
            dest = f.parent / a.move
            dest.mkdir(exist_ok=True)
            shutil.move(str(f), dest / f.name)
        print(f"moved {len(dead)} dead clips into '{a.move}/'")
    sys.exit(1 if dead else 0)


if __name__ == "__main__":
    main()
