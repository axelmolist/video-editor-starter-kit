"""
Caption track generator with ADAPTIVE outline.

Rule (from the brand): clean white text with NO outline on dark backgrounds; a thin
outline is applied only where the background under the caption is actually light.
Implemented by sampling the real luminance of the caption band per cue (one ffmpeg
pass), so it adapts to full-screen scene takeovers and footage alike.

Captions are emitted ONLY for talking-head windows (outside full-screen scene windows),
so they never collide with a scene's own labels. Source video is never cut.

BLOCKING: caption words are normalised to the configured spelling locale
(video/lib/spelling.py) - Scribe writes American. And an animation must never show
the same text as these captions at the same time: run video/lib/caption_dedupe.py on the
.ass this writes against the beats' on-screen text before compositing.

Usage:
  python captions.py <video> <transcript.json> <out.ass> [scene_windows.json]
  scene_windows.json = [[start,end], ...] video-time windows to suppress captions in.
"""
import json, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spelling import normalise_words

import kitconfig
_S = kitconfig.style()
CFG = _S["captions"]
FPS = _S["output"]["fps"]
PAL = _S["palette"]

# Per-job vertical override: some framings (e.g. tighter head-and-shoulders) need the
# caption band higher, just under the chin. CAPTION_Y env overrides the config y for
# THIS render only, without touching the global default.
if os.environ.get("CAPTION_Y"):
    CFG["y"] = int(os.environ["CAPTION_Y"])

# caption sampling band (x, y, w, h) in the 1080x1920 frame
BAND = (290, CFG["y"] - 75, 500, 150)


def region_luma(video):
    """One ffmpeg pass -> mean luminance (0-255) of the caption band per frame."""
    x, y, w, h = BAND
    cmd = ["ffmpeg", "-v", "error", "-i", video, "-vf",
           f"crop={w}:{h}:{x}:{y},scale=1:1,format=gray", "-f", "rawvideo", "-"]
    return list(subprocess.run(cmd, capture_output=True).stdout)


def ass_t(s):
    h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


def in_windows(ts, windows):
    return any(a <= ts < b for a, b in windows)


def ass_colour(hex_str):
    """#RRGGBB -> ASS &H00BBGGRR (opaque)."""
    h = hex_str.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def gen(video, transcript, out_ass, windows=()):
    words = normalise_words([w for w in json.load(open(transcript))["words"] if w.get("type") == "word"])
    luma = region_luma(video) if CFG["outline"] == "adaptive" else []
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= CFG["max_words"] or w["text"].rstrip()[-1:] in ".!?":
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)

    extra = [w.strip().lower() for w in os.environ.get("EXTRA_ACCENT_WORDS", "").split(",") if w.strip()]
    accent = set(CFG.get("accent_words", [])) | set(extra); ev = []
    acc = ass_colour(CFG.get("highlight_colour") or PAL["accent"])[4:]
    txt = ass_colour(CFG.get("text_colour") or PAL["text"])[4:]
    case = CFG.get("case", "as-spoken")
    for i, ch in enumerate(chunks):
        start = ch[0]["start"]
        if in_windows(start, windows): continue
        end = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else ch[-1]["end"] + 0.4
        end = min(end, start + 1.6)
        # adaptive outline: outline only if the band is light during this cue
        outline = 0
        if CFG["outline"] == "always":
            outline = CFG["outline_width_on_light"]
        elif CFG["outline"] == "adaptive" and luma:
            seg = luma[int(start * FPS):max(int(start * FPS) + 1, int(end * FPS))]
            if seg and sum(seg) / len(seg) > CFG["outline_luminance_threshold"]:
                outline = CFG["outline_width_on_light"]
        parts = []
        for w in ch:
            cl = w["text"].lower().strip('.,"\'?!-')
            t = w["text"].upper() if case == "upper" else w["text"].lower() if case == "lower" else w["text"]
            parts.append((r"{\c&H" + acc + "&}" + t + r"{\c&H" + txt + "&}") if cl in accent else t)
        tags = r"{\an5\pos(540," + str(CFG["y"]) + r")\bord" + str(outline) + r"\fad(40,40)"
        if CFG.get("kinetic"):
            tags += r"\fscx64\fscy64\t(0,90,\fscx100\fscy100)"
        tags += "}"
        ev.append(f"Dialogue: 0,{ass_t(start)},{ass_t(end)},Caps,,0,0,0,,{tags}{' '.join(parts)}")

    outline_col = ass_colour(CFG.get("outline_colour", "#000000"))
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, "
        "Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caps,{CFG['font']},{CFG['size']},&H00{txt},{outline_col},&H00000000,1,0,1,0,0,5,40,40,40,0\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    open(out_ass, "w").write(header + "\n".join(ev) + "\n")
    n_outlined = sum(1 for e in ev if r"\bord0" not in e)
    print(f"{out_ass}: {len(ev)} cues ({n_outlined} outlined for light backgrounds)")


if __name__ == "__main__":
    video, transcript, out_ass = sys.argv[1], sys.argv[2], sys.argv[3]
    windows = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else []
    gen(video, transcript, out_ass, windows)
