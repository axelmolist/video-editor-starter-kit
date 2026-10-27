#!/usr/bin/env python3
"""Render a long-form edit from a longform_timeline.json (video-agnostic).

Reusable by the `youtube-long-editor` agent for every solo long-form video. ALL
per-video data (source path, crop, grade, out path, the cut, cards, lower third)
lives in the JSON, which `build_timeline.py` produced. Run:

    python3 render_longform.py <edit_dir>/longform_timeline.json

Click-free audio pipeline (do not "simplify" this):
  - Each segment carries LOSSLESS PCM (no AAC encoder-delay priming -> the clicks).
  - 30ms afade in/out per segment -> every clip starts AND ends at ~0 amplitude, so
    concat joins are zero-to-zero and structurally click-free.
  - Cuts are already snapped into real silence by build_timeline.py.
  - The lower third is burned onto its own segment during extraction.
  - Lossless concat -> base.mkv -> ONE final pass: copy video, two-pass loudnorm the
    audio, encode AAC once -> <slug>-final.mp4.
"""
import json, subprocess, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

JSON = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("longform_timeline.json").resolve()
EDIT = JSON.parent
T = json.loads(JSON.read_text())
RAW = Path(T["source_path"]); FONT = Path(T["font_path"]); OUT = Path(T["out_path"])
CROP, GRADE = T["crop"], T["grade"]
SEGDIR = EDIT / "segments"; SEGDIR.mkdir(exist_ok=True)
FPS = T.get("fps", 25); FADE = 0.03
# Output is ALWAYS 4K (3840x2160) - source is 4K and the deliverable must stay 4K.
# Card/lower-third metrics are authored at a 1080 reference; F scales them to 4K.
OUTW, OUTH = T.get("out_w", 3840), T.get("out_h", 2160); F = OUTH / 1080.0
VENC = ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS)]
PCM = ["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]

def sh(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.stderr.write(" ".join(str(c) for c in cmd[:8]) + " ...\n" + r.stderr.decode()[-1500:] + "\n")
        raise SystemExit(f"ffmpeg failed ({r.returncode})")
    return r

def lower_third_filter(lt):
    a, b, f = lt["lstart"], lt["lend"], 0.3
    alpha = (f"alpha='if(between(t,{a:.2f},{b:.2f}),"
             f"if(lt(t,{a+f:.2f}),(t-{a:.2f})/{f},if(lt(t,{b-f:.2f}),1,({b:.2f}-t)/{f})),0)'")
    return (f",drawtext=fontfile='{FONT}':text='{lt['text']}':fontcolor=white:"
            f"fontsize={int(44*F)}:x=(w-text_w)/2:y={int(lt.get('y',748)*F)}:{alpha}")

def make_clip(i, it):
    out = SEGDIR / f"seg_{i:03d}.mkv"
    if it["type"] == "card":
        title = it["title"].replace("'", r"\'").replace(":", r"\:")
        dur = it["duration"]
        fade = f"alpha='if(lt(t,0.45),t/0.45,if(lt(t,{dur-0.45:.2f}),1,({dur:.2f}-t)/0.45))'"
        vf = ("noise=alls=12:allf=t,"
              f"drawtext=fontfile='{FONT}':text='{title}':fontcolor=white:fontsize={int(46*F)}:"
              f"x=(w-text_w)/2:y=(h-text_h)/2:{fade}")
        sh(["ffmpeg", "-y", "-f", "lavfi", "-i",
            f"gradients=s={OUTW}x{OUTH}:c0=0x18242e:c1=0x06090d:x0={int(960*F)}:y0={int(460*F)}:x1={int(300*F)}:y1={OUTH}:type=radial:d={dur}:r={FPS}",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf", vf, "-t", f"{dur}", *VENC, *PCM, "-shortest", str(out)])
    else:
        dur = round(it["src_end"] - it["src_start"], 3)
        fo = max(0.0, dur - FADE)
        af = f"afade=t=in:st=0:d={FADE},afade=t=out:st={fo:.3f}:d={FADE}"
        vf = f"{CROP},{GRADE}" + (lower_third_filter(it["lower_third"]) if it.get("lower_third") else "")
        sh(["ffmpeg", "-y", "-ss", f"{it['src_start']:.3f}", "-i", str(RAW), "-t", f"{dur:.3f}",
            "-vf", vf, "-af", af, *VENC, *PCM, str(out)])
    return out

def main():
    items = T["timeline"]
    print(f"rendering {len(items)} clips ...", flush=True)
    paths = [None] * len(items)
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(make_clip, i, it): i for i, it in enumerate(items)}
        done = 0
        for f in list(futs):
            paths[futs[f]] = f.result(); done += 1
            if done % 40 == 0: print(f"  {done}/{len(items)}", flush=True)
    lst = EDIT / "_concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in paths))
    base = EDIT / "base.mkv"
    print("concat -> base.mkv", flush=True)
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(base)])
    print("loudnorm pass 1 (measure)", flush=True)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(base),
        "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-vn", "-f", "null", "-"],
        capture_output=True, text=True)
    err = r.stderr; s = err.rfind("{"); e = err.rfind("}")
    m = json.loads(err[s:e+1])
    ln = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
          f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
          f":offset={m['target_offset']}:linear=true")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"final: copy video + loudnorm audio -> {OUT.name}", flush=True)
    sh(["ffmpeg", "-y", "-i", str(base), "-c:v", "copy", "-af", ln,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(OUT)])
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nk=1:nw=1", str(OUT)], capture_output=True, text=True).stdout.strip()
    print(f"\nDONE: {OUT}  ({float(dur):.1f}s, {OUT.stat().st_size/1e6:.0f} MB)", flush=True)

if __name__ == "__main__":
    main()
