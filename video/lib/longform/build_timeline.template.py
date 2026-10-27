#!/usr/bin/env python3
"""Build the cut timeline for ONE long-form video.

The youtube-long-editor agent copies this into <job>/project/edit/build_timeline.py
and fills the CONFIG block below. The silence-snapping logic underneath is generic -
do not change it. Produces longform_timeline.json for render_longform.py.

Prereqs in the same edit dir (the agent creates them):
  transcripts/<rawstem>.json   (Scribe word-level, via video-use transcribe.py)
  silences.json                (from silencedetect, see the agent doc)
"""
import json
from pathlib import Path

import sys
EDIT = Path(__file__).resolve().parent       # video/projects/youtube-long/<slug>/editor-files/edit/
SLUGDIR = EDIT.parents[1]                     # video/projects/youtube-long/<slug>/
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "video" / "lib"))   # repo video/lib
import kitconfig  # noqa: E402

# ============================ CONFIG (agent fills) ============================
SLUG = "vid-XX-slug"
RAW_FILE = "raw-footage.mov"                 # filename inside <slug>/raw-footage/
RAWSTEM = RAW_FILE.rsplit(".", 1)[0]         # transcript json stem

# Reframe crop, MEASURED per recording with a thirds grid (head centred, eyes on the
# upper-third line, modest punch-in). 16:9 window from the 4K source, then scale back
# to FULL 4K. OUTPUT IS ALWAYS 3840x2160 - footage is 4K in, 4K out, never less.
# (Reframing means a mild upscale of the cropped window to 4K; that is expected.)
CROP = "crop=3264:1836:252:100,scale=3840:2160"

# The house grade from style-config.json (built with the colour-grader agent). Empty =
# no grade; set "null" filter so ffmpeg still has a valid chain.
GRADE = kitconfig.style()["grade"].get("ffmpeg_filter") or "null"

CARD_DUR = 2.5                               # section card seconds on screen (2-3s)
# Source span (seconds) of the spoken website/CTA delivery, for the
# lower third. Find it in the transcript. Set to None if the video has no URL mention.
URL_SRC = (0.0, 0.0)

# The CUT. Ordered list of beats = the FINAL/best take of each script line, in order.
# Each beat is (approx_lo, approx_hi, "label"); a "CARD::Title" entry inserts a
# section card. The lo/hi only need to BRACKET the chosen take's speech - cuts are
# snapped to real silence inside. Pick the LAST take of any repeated line (unless the
# latest is broken mid-sentence -> last complete take). Exclude section read-outs
# (replace each with a CARD). Watch for word DOUBLING when two beats share a word.
BEATS = [
    (11.8, 19.5, "example beat one"),
    (27.2, 32.2, "example beat two"),
    ("CARD::The section title",),
    # ... author the full cut here from takes_packed.md vs the script ...
]
# =============================================================================

RAW_PATH = SLUGDIR / "raw-footage" / RAW_FILE
FONT_PATH = kitconfig.font_file("body")
URL_TEXT = kitconfig.brand().get("website", "example.com")
OUT_PATH = SLUGDIR / "final-footage" / f"{SLUG}-final.mp4"

WORDS = [w for w in json.loads((EDIT / "transcripts" / f"{RAWSTEM}.json").read_text()).get("words", [])
         if w.get("type") == "word" and w.get("start") is not None]
SIL = json.loads((EDIT / "silences.json").read_text())   # [[start,end,dur],...] sorted

SPLIT = 0.15     # a silence longer than this is a reading pause -> cut it down
LEAD = 0.05      # silence kept before a segment's first word
TRAIL = 0.05     # silence kept after a segment's last word  (LEAD+TRAIL ~= max gap)
ADJ = 0.35       # snap to a silence within this of the cut
EPS = 0.006

def sil_end_before(t, lo):
    best = None
    for s, e, _ in SIL:
        if lo - 0.4 <= e <= t + 0.06 and (best is None or e > best[1]):
            best = (s, e)
    return best

def sil_start_after(t, hi):
    best = None
    for s, e, _ in SIL:
        if t - 0.06 <= s <= hi + 0.02 and (best is None or s < best[0]):
            best = (s, e)
    return best

def build_segments(lo, hi, max_internal=SPLIT):
    """Keep all speech in [lo,hi]; cut every silence > max_internal; snap each edge
    INTO an adjacent detected silence (clean, voice-safe); gap-less grafts cut at the
    boundary and rely on the render fade."""
    big = sorted((max(s, lo), min(e, hi)) for s, e, d in SIL
                 if d > max_internal and e > lo + EPS and s < hi - EPS)
    blocks, cursor = [], lo
    for bs, be in big:
        if bs - cursor > 0.04:
            blocks.append((cursor, bs))
        cursor = max(cursor, be)
    if hi - cursor > 0.04:
        blocks.append((cursor, hi))
    segs = []
    for a, b in blocks:
        sp = sil_end_before(a, lo)
        start = min(a - LEAD, sp[1] - 0.02) if (sp and a - sp[1] < ADJ) else a - 0.02
        if sp and a - sp[1] < ADJ:
            start = max(start, sp[0] + 0.01)
        sn = sil_start_after(b, hi)
        if sn and sn[0] - b < ADJ:
            end = max(min(b + TRAIL, sn[0] + TRAIL, sn[1] - 0.01), sn[0] + 0.01)
        else:
            end = b + 0.02
        if end - start < 0.05:
            continue
        segs.append((round(max(0.0, start), 3), round(end, 3)))
    return segs or [(round(lo, 3), round(hi, 3))]

timeline = []
for bt in BEATS:
    if isinstance(bt[0], str) and bt[0].startswith("CARD::"):
        timeline.append({"type": "card", "title": bt[0][6:], "duration": CARD_DUR})
        continue
    lo, hi, label = bt
    is_cta = URL_SRC and (lo < URL_SRC[1] and hi > URL_SRC[0])
    for (s, e) in build_segments(lo, hi, max_internal=1.0 if is_cta else SPLIT):
        item = {"type": "clip", "src_start": s, "src_end": e, "label": label, "dur": round(e - s, 3)}
        if URL_SRC and s < URL_SRC[1] and e > URL_SRC[0]:
            ls, le = max(0.0, URL_SRC[0] - s), min(e - s, URL_SRC[1] - s)
            if le - ls > 0.4:
                item["lower_third"] = {"text": URL_TEXT, "lstart": round(ls, 3),
                                       "lend": round(le, 3), "y": 748}
        timeline.append(item)

out_t = 0.0
for item in timeline:
    item["out_start"] = round(out_t, 3)
    out_t += item["duration"] if item["type"] == "card" else item["dur"]
    item["out_end"] = round(out_t, 3)

lower_third = next(({"text": it["lower_third"]["text"],
                     "out_start": round(it["out_start"] + it["lower_third"]["lstart"], 3),
                     "out_end": round(it["out_start"] + it["lower_third"]["lend"], 3)}
                   for it in timeline if it.get("lower_third")), None)

out = {"slug": SLUG, "source_path": str(RAW_PATH), "font_path": str(FONT_PATH),
       "out_path": str(OUT_PATH), "fps": kitconfig.style()["output"]["fps"], "crop": CROP, "grade": GRADE,
       "timeline": timeline, "lower_third": lower_third, "total_duration_s": round(out_t, 3)}
(EDIT / "longform_timeline.json").write_text(json.dumps(out, indent=1))
clips = sum(1 for x in timeline if x["type"] == "clip")
cards = sum(1 for x in timeline if x["type"] == "card")
print(f"clips: {clips}  cards: {cards}  total: {int(out_t//60)}m {out_t%60:04.1f}s")
print("lower third:", lower_third)
