#!/usr/bin/env python3
"""Caption / animation-text de-duplication gate.

BLOCKING rule: on every video (shorts, long-form, podcast clips, vlogs, highlights) an animation or
graphic must NEVER show the same text as the captions on screen at the same time. One of them gives way:
  - DEFAULT: rewrite or remove the animation's text, keep the visual (captions carry the spoken words).
  - EXCEPTION: when the text IS the point of the beat (quote card, typography beat, receipt headline), suppress the
    captions for that window - then the captions are gone and this gate passes.

API (stable - other pipelines import it):
    find_overlaps(captions, anim_texts, min_words=2, window_pad=0.5) -> list[dict]
    gate(captions, anim_texts, **kw) -> int        # prints overlaps, returns 1 on any, 0 when clean
    load_captions(path) -> list[{start, end, text}] # .json / .srt / .vtt / .ass, or ElevenLabs words JSON
    load_anim_texts(path) -> list[{id, start, end, text}]

captions:   [{start, end, text}]         (seconds, the times the caption is ON SCREEN in the output)
anim_texts: [{start, end, text, id?}]    (seconds, the times that text is ON SCREEN in the output)

Matching (both sides normalised: lowercase, one canonical (British) spelling so "color" matches "colour", punctuation stripped, "75 percent" /
"75 per cent" -> "75%", whitespace collapsed). Only captions on screen inside the anim window +/- window_pad count:
  run        the anim text shares >= min_words consecutive words with a caption (or with the captions that are on
             screen during the window read in order), and the run holds at least one non-stopword ("of the" alone
             never fires)
  contained  the anim's whole text appears in a caption and is either a number/percentage (75%, £20m, 2026) or
             a single word of 4+ characters ("Project", "Scheduled")

CLI (pre-render gate):
    python3 video/lib/caption_dedupe.py <captions.json|.srt|.ass|.vtt> <anim_texts.json> [--min-words 2]
        [--pad 0.5] [--json]
    exit 0 = clean, 1 = overlaps (blocking), 2 = bad input
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from british_english import to_british as _canon  # noqa: E402 - one canonical spelling for matching, whatever the locale

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "so", "of", "to", "in", "on", "at", "for", "with", "by", "from", "as", "is",
    "it", "its", "it's", "this", "that", "these", "those", "be", "was", "were", "are", "am", "i", "you", "we", "they",
    "he", "she", "me", "my", "your", "our", "their", "his", "her", "them", "us", "do", "did", "does", "done", "not",
    "no", "yes", "if", "then", "than", "there", "here", "what", "which", "who", "how", "when", "where", "why", "just",
    "really", "very", "up", "out", "about", "into", "over", "all", "can", "could", "would", "will", "should", "have",
    "has", "had", "get", "got", "go", "going", "like", "know", "think", "one", "some", "any", "more", "most", "also",
    "too", "now", "well", "oh", "um", "uh", "yeah", "okay", "ok", "dont", "im", "thats", "youre", "were", "theyre",
    "ive", "id", "ill", "isnt", "its",
}

_ASS_TAG = re.compile(r"\{\\[^}]*\}")
_MARKUP = re.compile(r"[{}~]")


def norm_tokens(text):
    """Normalised token list."""
    t = _ASS_TAG.sub(" ", str(text or ""))
    t = t.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ")
    t = _MARKUP.sub(" ", t)
    t = _canon(t).lower()
    t = re.sub(r"[‘’']", "", t)                       # don't -> dont
    t = re.sub(r"(\d)\s*(?:per\s*cent|percent)\b", r"\1%", t)
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)                   # 1,000 -> 1000
    t = re.sub(r"[^\w%.\s]", " ", t)                            # keep %, decimal points
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)                   # dots that are not decimal points
    return t.split()


def norm(text):
    return " ".join(norm_tokens(text))


def _is_number(tok):
    """75%, 20m, 1.5, 2026, 10x, 3k - not product names like mp4 / gpt5."""
    return bool(re.fullmatch(r"\d[\d.]*(?:%|k|m|bn|x|s|st|nd|rd|th)?", tok))


def _longest_run(a, b):
    """Longest common contiguous token run between a and b -> (length, start_in_a)."""
    best, best_i = 0, 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, best_i = cur[j], i - cur[j]
        prev = cur
    return best, best_i


def _runs(a, b, min_words):
    """Every maximal common run of >= min_words tokens that holds a content word -> list of token lists."""
    out = []
    for i in range(len(a)):
        for j in range(len(b)):
            if a[i] != b[j] or (i > 0 and j > 0 and a[i - 1] == b[j - 1]):
                continue
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            if k >= min_words:
                run = a[i:i + k]
                if any(t not in STOPWORDS for t in run):
                    out.append(run)
    return out


def _contains(hay, needle):
    n = len(needle)
    return n > 0 and any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def _f(x, *keys):
    for k in keys:
        if isinstance(x, dict) and x.get(k) is not None:
            return x[k]
    return None


def _anim_text(a):
    t = _f(a, "text", "on_screen_text", "label", "title")
    if isinstance(t, (list, tuple)):
        t = " / ".join(str(x) for x in t)
    return t or ""


def find_overlaps(captions, anim_texts, min_words=2, window_pad=0.5):
    """Records for every anim text that duplicates caption text on screen at the same time:
    {anim_id, anim_text, anim_start, anim_end, caption_text, caption_start, caption_end, matched, rule}."""
    caps = []
    for c in captions or []:
        s, e = _f(c, "start", "t0", "in"), _f(c, "end", "t1", "out")
        if s is None or e is None:
            continue
        caps.append((float(s), float(e), str(_f(c, "text", "caption") or "")))
    caps.sort(key=lambda c: c[0])
    out, seen = [], set()
    for idx, a in enumerate(anim_texts or []):
        s, e = _f(a, "start", "t0", "in"), _f(a, "end", "t1", "out")
        text = _anim_text(a)
        if s is None or e is None or not text.strip():
            continue
        s, e = float(s), float(e)
        aid = _f(a, "id", "beat", "name") or f"anim{idx + 1}"
        lo, hi = s - window_pad, e + window_pad
        live = [c for c in caps if c[0] < hi and c[1] > lo]
        if not live:
            continue
        # each line of a multi-line anim is its own piece of on-screen text
        pieces = [p for p in re.split(r"\s*(?:\n|\\N| / |\|)\s*", text) if p.strip()] or [text]
        joined = []
        for c in live:
            joined += norm_tokens(c[2])
        for piece in pieces:
            at = norm_tokens(piece)
            if not at:
                continue
            hit = None
            # 1) a run shared with ONE caption (most specific report)
            for c in live:
                runs = _runs(at, norm_tokens(c[2]), min_words)
                if runs:
                    best = max(runs, key=len)
                    hit = (c, " ".join(best), "run"); break
            # 2) a run across the captions on screen during the window, read in order
            if not hit:
                runs = _runs(at, joined, min_words)
                if runs:
                    best = max(runs, key=len)
                    hit = ((live[0][0], live[-1][1], " | ".join(c[2] for c in live)), " ".join(best), "run")
            # 3) the whole anim text contained: numbers of any length, single words of 4+ characters
            if not hit:
                short_ok = (len(at) == 1 and (_is_number(at[0]) or len(at[0]) >= 4)) or \
                           (len(at) > 1 and all(_is_number(t) for t in at))
                if short_ok:
                    for c in live:
                        if _contains(norm_tokens(c[2]), at):
                            hit = (c, " ".join(at), "contained"); break
            if hit:
                c, matched, rule = hit
                key = (aid, matched, round(s, 2))
                if key in seen:
                    continue
                seen.add(key)
                out.append({"anim_id": aid, "anim_text": piece.strip(), "anim_start": round(s, 3),
                            "anim_end": round(e, 3), "caption_text": c[2], "caption_start": round(c[0], 3),
                            "caption_end": round(c[1], 3), "matched": matched, "rule": rule})
    return out


def format_overlaps(overlaps):
    lines = []
    for o in overlaps:
        lines.append(f"  [{o['anim_id']}] {o['anim_start']:.2f}-{o['anim_end']:.2f}s anim \"{o['anim_text']}\"\n"
                     f"      caption {o['caption_start']:.2f}-{o['caption_end']:.2f}s \"{o['caption_text']}\"\n"
                     f"      duplicated ({o['rule']}): \"{o['matched']}\"")
    return "\n".join(lines)


def gate(captions, anim_texts, **kw):
    """Pre-render gate: prints the overlaps; returns 1 if any (BLOCKING), 0 when clean."""
    ov = find_overlaps(captions, anim_texts, **kw)
    if not ov:
        print(f"caption-dedupe: clean ({len(anim_texts or [])} anim texts vs {len(captions or [])} captions)")
        return 0
    print(f"caption-dedupe: BLOCKED - {len(ov)} animation text(s) duplicate the captions on screen.\n"
          "  Default fix: rewrite or remove the animation's text (keep the visual). Exception: if the text IS the beat\n"
          "  (quote card, typography beat, receipt headline), suppress the captions for that window instead.")
    print(format_overlaps(ov))
    return 1


# --------------------------------------------------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------------------------------------------------
def _secs_hms(s):
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    v = 0.0
    for p in parts:
        v = v * 60 + float(p)
    return v


def captions_from_ass(text):
    """Dialogue events -> [{start, end, text}] (override tags stripped; duplicate shadow layers merged)."""
    out, seen = [], set()
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(":", 1)[1].split(",", 9)
        if len(parts) < 10:
            continue
        s, e = _secs_hms(parts[1]), _secs_hms(parts[2])
        t = _ASS_TAG.sub("", parts[9]).replace("\\N", " ").strip()
        key = (round(s, 2), round(e, 2), t)
        if t and key not in seen:
            seen.add(key); out.append({"start": s, "end": e, "text": t})
    return out


def captions_from_srt(text):
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        m = re.search(r"(\d[\d:.,]+)\s*-->\s*(\d[\d:.,]+)[^\n]*\n(.*)", block, re.S)
        if m:
            t = re.sub(r"<[^>]+>", "", m.group(3)).replace("\n", " ").strip()
            if t:
                out.append({"start": _secs_hms(m.group(1)), "end": _secs_hms(m.group(2)), "text": t})
    return out


def _from_json(d, kind):
    if isinstance(d, dict):
        for k in (["captions", "cues", "subtitles", "words", "segments"] if kind == "cap" else
                  ["anim_texts", "anims", "animations", "beats", "graphics", "overlays", "texts"]):
            if isinstance(d.get(k), list):
                d = d[k]; break
    if not isinstance(d, list):
        raise ValueError(f"no {kind} list found")
    out = []
    for x in d:
        if isinstance(x, (list, tuple)) and len(x) >= 3:          # [text, start, end] (podcast cue shape)
            out.append({"text": x[0], "start": x[1], "end": x[2]})
        elif isinstance(x, dict):
            if kind == "cap" and x.get("type") in ("spacing", "audio_event"):
                continue
            out.append(x)
    return out


def load_captions(path):
    raw = open(path, encoding="utf-8").read()
    low = path.lower()
    if low.endswith(".ass") or low.endswith(".ssa"):
        return captions_from_ass(raw)
    if low.endswith(".srt") or low.endswith(".vtt"):
        return captions_from_srt(raw)
    return _from_json(json.loads(raw), "cap")


def load_anim_texts(path):
    return _from_json(json.load(open(path, encoding="utf-8")), "anim")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Pre-render gate: animation text must not duplicate on-screen captions")
    ap.add_argument("captions", help="captions .json/.srt/.vtt/.ass (or ElevenLabs words JSON)")
    ap.add_argument("anim_texts", help="anim texts .json: [{id, start, end, text}] (or {anim_texts: [...]})")
    ap.add_argument("--min-words", type=int, default=2)
    ap.add_argument("--pad", type=float, default=0.5, help="window pad in seconds (default 0.5)")
    ap.add_argument("--json", action="store_true", help="print the overlap records as JSON")
    a = ap.parse_args(argv)
    try:
        caps, anims = load_captions(a.captions), load_anim_texts(a.anim_texts)
    except (OSError, ValueError) as exc:
        print(f"caption-dedupe: bad input: {exc}", file=sys.stderr)
        return 2
    if a.json:
        ov = find_overlaps(caps, anims, min_words=a.min_words, window_pad=a.pad)
        print(json.dumps(ov, indent=1, ensure_ascii=False))
        return 1 if ov else 0
    return gate(caps, anims, min_words=a.min_words, window_pad=a.pad)


if __name__ == "__main__":
    sys.exit(main())
