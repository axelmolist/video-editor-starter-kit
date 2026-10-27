"""Podcast episode - render the episode cut from edl.json.

  1. Extract every video segment (frame-accurate, re-encoded to a uniform 4K h264).
  2. Verify each segment's frame count; re-encode the bad ones SERIALLY
     (VideoToolbox -12912 errors come from too many concurrent HW encode sessions).
  3. Concat segments (stream copy) -> video-only.
  4. Build audio in ONE sample-exact pass over full-audio.wav.
  5. Mux -> <edit-dir>/<episode>-cut-4k.mov.

Half-frame seek bias guarantees the correct first frame regardless of float rounding.

Usage:
  python render.py --episode-dir <eX> --edit-dir <work> [--workers 4] [--name e2-jamie]
"""
from __future__ import annotations
import argparse, json, subprocess
import concurrent.futures as cf
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--episode-dir", required=True, type=Path)
ap.add_argument("--edit-dir", required=True, type=Path)
ap.add_argument("--name", default="episode", help="output basename")
ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--bitrate", default="40M")
ap.add_argument("--fps", type=float, default=25.0,
                help="Source/output framerate (house standard 25; MUST match the camera fps for drift-free frame-lock). Pass 30 only for legacy 30fps footage.")
ap.add_argument("--stage", default="all", choices=["all", "extract", "post"])
A = ap.parse_args()

EP, ED, FPS = A.episode_dir.resolve(), A.edit_dir.resolve(), A.fps
TS = str(int(round(FPS * 1000)))  # video_track_timescale = 1000*fps (25->25000, 30->30000)
SEGDIR = ED / "segs"; SEGDIR.mkdir(parents=True, exist_ok=True)
FULL_AUDIO = EP / "full-audio.wav"
edl = json.loads((ED / "edl.json").read_text())
segs, keeps = edl["video_edl"], edl["audio_keeps"]
VENC = ["-c:v", "h264_videotoolbox", "-b:v", A.bitrate, "-maxrate", "55M", "-bufsize", "80M",
        "-pix_fmt", "yuv420p", "-r", str(int(round(FPS))), "-video_track_timescale", TS]

def segp(i): return SEGDIR / f"seg_{i:05d}.mov"
def nframes(p):
    if not p.exists(): return None
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    return int(r.stdout.strip()) if r.stdout.strip().isdigit() else None

def extract(i, capture=False):
    p = segs[i]; n = p["out_f"] - p["in_f"]
    ss = max(0.0, (p["in_f"] - 0.5) / FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", repr(ss), "-i", str(EP / p["src"]),
           "-frames:v", str(n), "-an", *VENC, str(segp(i))]
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True).returncode
    if segp(i).exists() and nframes(segp(i)) == n:
        return (i, "cached")
    subprocess.run(cmd, check=True)
    return (i, "ok")

def step_extract():
    print(f"[1/5] extracting {len(segs)} segments ({A.workers} workers)...", flush=True)
    done = 0
    with cf.ThreadPoolExecutor(max_workers=A.workers) as ex:
        for f in cf.as_completed([ex.submit(extract, i) for i in range(len(segs))]):
            f.result(); done += 1
            if done % 100 == 0 or done == len(segs):
                print(f"  {done}/{len(segs)}", flush=True)

def step_verify_repair():
    print("[2/5] verifying frame counts...", flush=True)
    bad = [i for i, p in enumerate(segs) if nframes(segp(i)) != p["out_f"] - p["in_f"]]
    print(f"  bad/missing: {len(bad)}", flush=True)
    if bad:
        print(f"  repairing {len(bad)} serially...", flush=True)
        for n, i in enumerate(bad, 1):
            extract(i, capture=True)
            got = nframes(segp(i)); exp = segs[i]["out_f"] - segs[i]["in_f"]
            print(f"    [{n}/{len(bad)}] seg_{i:05d}: {got}/{exp} {'OK' if got == exp else 'STILL BAD'}", flush=True)
        still = [i for i in bad if nframes(segp(i)) != segs[i]["out_f"] - segs[i]["in_f"]]
        if still:
            raise SystemExit(f"segments still bad after repair: {still}")

def step_post():
    print("[3/5] concat video...", flush=True)
    (ED / "concat_list.txt").write_text("".join(f"file '{segp(i)}'\n" for i in range(len(segs))))
    vonly = ED / "video_only.mov"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(ED / "concat_list.txt"), "-c", "copy",
                    "-video_track_timescale", TS, str(vonly)], check=True)
    print("[4/5] build audio (sample-exact)...", flush=True)
    parts = [f"[0:a]atrim=start={k['in']:.9f}:end={k['out']:.9f},asetpts=PTS-STARTPTS[a{j}]"
             for j, k in enumerate(keeps)]
    graph = ";".join(parts) + ";" + "".join(f"[a{j}]" for j in range(len(keeps))) + f"concat=n={len(keeps)}:v=0:a=1[out]"
    (ED / "audio_filter.txt").write_text(graph)
    aud = ED / "audio.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(FULL_AUDIO),
                    "-filter_complex_script", str(ED / "audio_filter.txt"), "-map", "[out]",
                    "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2", str(aud)], check=True)
    print("[5/5] mux...", flush=True)
    out = ED / f"{A.name}-cut-4k.mov"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vonly), "-i", str(aud),
                    "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-dn", "-map_metadata", "-1",
                    "-movflags", "+faststart", str(out)], check=True)
    print("DONE:", out)

if A.stage in ("all", "extract"):
    step_extract(); step_verify_repair()
if A.stage in ("all", "post"):
    step_post()
