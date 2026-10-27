"""Podcast episode - prepend a YouTube-style hook + the shared jingle to the episode cut.

Final structure:  [ hook clips ]  ->  [ show intro jingle ]  ->  [ episode cut ]

Hook clips are guest close-ups (guest-shot) with audio from full-audio.wav. Each clip may
be made of several sub-ranges (e.g. to splice out a stumble). All pieces are encoded to the
same spec as the episode so the final concat is a clean stream copy (episode is NOT re-encoded).

hook.json schema (written by the agent after choosing clips from the transcript):
  { "clips": [ [[in,out],[in,out]], [[in,out]], ... ] }   # seconds; outer=clips, inner=sub-ranges

Usage:
  python build_hook.py --episode-dir <eX> --edit-dir <work> --episode-cut <file.mov> \
        --intro <show-intro.mov> --hook <hook.json> --captions <hook_caps.ass> --out <FINAL.mov>

--captions is optional but DEFAULT for this show: burns the high-energy ASS captions onto
the hook before assembly (the hook is the only re-encode; the 48-min episode is stream-copied).
"""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--episode-dir", required=True, type=Path)
ap.add_argument("--edit-dir", required=True, type=Path)
ap.add_argument("--episode-cut", required=True, type=Path)
ap.add_argument("--intro", required=True, type=Path)
ap.add_argument("--hook", required=True, type=Path)
ap.add_argument("--out", required=True, type=Path)
ap.add_argument("--captions", type=Path, default=None, help="ASS file to burn on the hook")
ap.add_argument("--fonts", type=Path,
                default=Path(__file__).resolve().parents[1].parent / "fonts",
                help="fontsdir for libass (default video/fonts)")
ap.add_argument("--bitrate", default="40M")
ap.add_argument("--fps", type=float, default=25.0,
                help="Source/output framerate (house standard 25; MUST match the camera fps). Pass 30 only for legacy 30fps footage.")
A = ap.parse_args()

EP, ED, FPS = A.episode_dir.resolve(), A.edit_dir.resolve(), A.fps
TS = str(int(round(FPS * 1000)))  # video_track_timescale = 1000*fps (25->25000, 30->30000)
GUEST, FULL_AUDIO = EP / "guest-shot-4k.mov", EP / "full-audio.wav"
VENC = ["-c:v", "h264_videotoolbox", "-b:v", A.bitrate, "-maxrate", "55M", "-bufsize", "80M",
        "-pix_fmt", "yuv420p", "-r", str(int(round(FPS))), "-video_track_timescale", TS]
AENC = ["-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2"]
TMP = ED / "hook_tmp"; TMP.mkdir(parents=True, exist_ok=True)
def F(t): return int(round(t * FPS))
def run(c): subprocess.run(c, check=True)

clips = json.loads(A.hook.read_text())["clips"]
ranges = [(F(a), F(b)) for clip in clips for (a, b) in clip]  # flattened, in order

print(f"[1] {len(ranges)} hook video pieces (guest close-up)")
vparts = []
for i, (a, b) in enumerate(ranges):
    ss = max(0.0, (a - 0.5) / FPS)
    o = TMP / f"hook_v_{i}.mov"
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", repr(ss), "-i", str(GUEST),
         "-frames:v", str(b - a), "-an", *VENC, str(o)])
    vparts.append(o)

print("[2] hook audio (sample-exact)")
parts = [f"[0:a]atrim=start={a/FPS:.9f}:end={b/FPS:.9f},asetpts=PTS-STARTPTS[a{i}]"
         for i, (a, b) in enumerate(ranges)]
graph = ";".join(parts) + ";" + "".join(f"[a{i}]" for i in range(len(ranges))) + f"concat=n={len(ranges)}:v=0:a=1[out]"
(TMP / "hook_af.txt").write_text(graph)
run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(FULL_AUDIO),
     "-filter_complex_script", str(TMP / "hook_af.txt"), "-map", "[out]", *AENC, str(TMP / "hook_audio.m4a")])

print("[3] assemble hook.mov")
(TMP / "hook_vlist.txt").write_text("".join(f"file '{p}'\n" for p in vparts))
run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(TMP / "hook_vlist.txt"),
     "-c", "copy", "-video_track_timescale", TS, str(TMP / "hook_video.mov")])
hook = ED / "hook.mov"
run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(TMP / "hook_video.mov"), "-i", str(TMP / "hook_audio.m4a"),
     "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-dn", "-map_metadata", "-1", str(hook)])

front = hook
if A.captions:
    print("[3b] burn high-energy captions onto hook")
    cap = ED / "hook_captioned.mov"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(hook),
         "-vf", f"subtitles={A.captions.resolve()}:fontsdir={A.fonts.resolve()}",
         *VENC, "-map", "0:v:0", "-map", "0:a:0", "-c:a", "copy", str(cap)])
    front = cap

print("[4] standardise intro jingle")
intro_std = TMP / "intro_std.mov"
run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(A.intro.resolve()),
     "-map", "0:v:0", "-map", "0:a:0", *VENC, *AENC, "-dn", "-map_metadata", "-1", str(intro_std)])

print("[5] final concat -> hook + jingle + episode")
(ED / "final_list.txt").write_text("".join(f"file '{p}'\n" for p in [front, intro_std, A.episode_cut.resolve()]))
run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(ED / "final_list.txt"),
     "-c", "copy", "-movflags", "+faststart", str(A.out.resolve())])
print("DONE:", A.out.resolve())
