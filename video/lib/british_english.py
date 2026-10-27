#!/usr/bin/env python3
"""British English normaliser for captions, transcripts and on-screen text.

Used by spelling.py when config/brand.json "locale" is a British-spelling variant.
ElevenLabs Scribe only takes language_code "en"/"eng" (no en-GB), so it writes "realize", "color", "center".
We normalise on OUR side, after transcription, at the point words become caption text. Never edit
the video-use skill (third-party); call this instead.

API (stable - other pipelines import it):
    to_british(text) -> str
    normalise_words(words, key="text") -> list[dict]        # ElevenLabs word lists, timings untouched
    normalise_transcript_file(path_in, path_out=None) -> str  # .json (ElevenLabs shape) or text (.txt/.srt/.vtt/.ass/.md)
    find_americanisms(text) -> list[tuple[str, str]]          # [(found, british)], for --check

CLI:
    python3 video/lib/british_english.py <file.json|file.txt|-> [--check] [-o OUT | --in-place]
        default    print the normalised content to stdout
        --check    list American spellings found, exit 1 if any (nothing is written)

Design: a curated map plus a guarded -ize/-yze/-ization rule with an exception list (size, prize, seize, capsize,
maize...). URLs, @handles, #hashtags, `code`, {ASS tags}, CamelCase product names (OpenAI, HighLevel), tokens with
digits/underscores/slashes and a list of protected proper nouns (Center Parcs, Final Cut Pro, Color Board, Pearl
Harbor...) are never touched. Context-dependent words (program, check, tire, license, practice, meter, dialog,
draft, artifact, gotten) are deliberately skipped. False negatives beat false positives.
"""
import bisect
import copy
import json
import os
import re
import sys

# --------------------------------------------------------------------------------------------------------------------
# Curated map (lowercase American -> British). Inflections are generated below.
# --------------------------------------------------------------------------------------------------------------------
_MAP = {}


def _add(us, gb):
    _MAP[us] = gb


# -or -> -our (only the inflections that are actually spelled differently; humorous/vigorous/honorary stay)
_OR = ["color", "behavior", "favor", "honor", "humor", "labor", "neighbor", "rumor", "flavor", "harbor", "endeavor",
       "vapor", "odor", "armor", "parlor", "candor", "splendor", "clamor", "savior", "valor", "ardor", "fervor",
       "tumor", "demeanor", "rigor", "succor"]
_OR_SUFFIXES = ["", "s", "ed", "ing", "ful", "fully", "less", "able", "ably", "er", "ers", "hood", "hoods", "y"]
for w in _OR:
    for suf in _OR_SUFFIXES:
        _add(w + suf, w[:-2] + "our" + suf)
# colorize & co. (the -ize rule alone would leave the "color" part)
for suf in ["ize", "izes", "ized", "izing", "ization"]:
    _add("color" + suf, "colour" + suf.replace("iz", "is"))
_add("colorway", "colourway"); _add("colorways", "colourways")
for w in ["favorite", "favorites", "favoritism", "behavioral", "behaviorally", "behaviorist", "colorist", "colorists",
          "laborer", "laborers"]:
    _add(w, w.replace("or", "our", 1))
# humorous, humorist, honorary, laborious, vigorous, odorous, humoral: spelled the same in both - never generated.

# -er -> -re
for us, gb in [("center", "centre"), ("theater", "theatre"), ("fiber", "fibre"), ("liter", "litre"),
               ("caliber", "calibre"), ("somber", "sombre"), ("saber", "sabre"), ("meager", "meagre"),
               ("luster", "lustre"), ("specter", "spectre"), ("scepter", "sceptre"), ("sepulcher", "sepulchre"),
               ("centimeter", "centimetre"), ("millimeter", "millimetre"), ("kilometer", "kilometre")]:
    _add(us, gb); _add(us + "s", gb + "s")
for us, gb in [("centered", "centred"), ("centering", "centring"), ("centerpiece", "centrepiece"),
               ("centerpieces", "centrepieces"), ("centerline", "centreline"), ("centerfold", "centrefold"),
               ("fiberglass", "fibreglass"), ("fiberoptic", "fibreoptic"), ("theatergoer", "theatregoer")]:
    _add(us, gb)

# -ense -> -ence
for us, gb in [("defense", "defence"), ("offense", "offence"), ("pretense", "pretence")]:
    _add(us, gb); _add(us + "s", gb + "s")
_add("defenseless", "defenceless")

# doubled L before a suffix (explicit forms only)
for us, gb in [
    ("traveled", "travelled"), ("traveling", "travelling"), ("traveler", "traveller"), ("travelers", "travellers"),
    ("canceled", "cancelled"), ("canceling", "cancelling"), ("cancelation", "cancellation"),
    ("cancelations", "cancellations"), ("labeled", "labelled"), ("labeling", "labelling"),
    ("modeled", "modelled"), ("modeling", "modelling"), ("modeler", "modeller"), ("modelers", "modellers"),
    ("fueled", "fuelled"), ("fueling", "fuelling"), ("leveled", "levelled"), ("leveling", "levelling"),
    ("signaled", "signalled"), ("signaling", "signalling"), ("marveled", "marvelled"), ("marveling", "marvelling"),
    ("marvelous", "marvellous"), ("counseled", "counselled"), ("counseling", "counselling"),
    ("counselor", "counsellor"), ("counselors", "counsellors"), ("totaled", "totalled"), ("totaling", "totalling"),
    ("channeled", "channelled"), ("channeling", "channelling"), ("tunneled", "tunnelled"),
    ("tunneling", "tunnelling"), ("quarreled", "quarrelled"), ("quarreling", "quarrelling"),
    ("jeweler", "jeweller"), ("jewelers", "jewellers"), ("jewelry", "jewellery"), ("dialed", "dialled"),
    ("dialing", "dialling"), ("paneled", "panelled"), ("paneling", "panelling"), ("pedaled", "pedalled"),
    ("pedaling", "pedalling"), ("unraveled", "unravelled"), ("unraveling", "unravelling"),
    ("groveled", "grovelled"), ("groveling", "grovelling"), ("swiveled", "swivelled"),
    ("funneled", "funnelled"), ("funneling", "funnelling"), ("refueled", "refuelled"),
    ("refueling", "refuelling"), ("enrollment", "enrolment"), ("enrollments", "enrolments"),
    ("fulfillment", "fulfilment"), ("installment", "instalment"), ("installments", "instalments"),
    ("skillful", "skilful"), ("skillfully", "skilfully"), ("willful", "wilful"), ("willfully", "wilfully"),
    ("fulfill", "fulfil"), ("fulfills", "fulfils"), ("enroll", "enrol"), ("enrolls", "enrols"),
    ("instill", "instil"), ("instills", "instils"),
]:
    _add(us, gb)

# practise as a verb (only the unambiguous verb forms; "practice" itself is skipped)
for us, gb in [("practiced", "practised"), ("practicing", "practising")]:
    _add(us, gb)

# -og -> -ogue (dialog is skipped: "dialog box" is common British computing usage)
for us, gb in [("catalog", "catalogue"), ("catalogs", "catalogues"), ("cataloged", "catalogued"),
               ("cataloging", "cataloguing"), ("analog", "analogue"), ("monolog", "monologue"),
               ("monologs", "monologues"), ("epilog", "epilogue"), ("prolog", "prologue")]:
    _add(us, gb)

# -yze handled by rule; -ment / -e
for us, gb in [("judgment", "judgement"), ("judgments", "judgements"), ("acknowledgment", "acknowledgement"),
               ("acknowledgments", "acknowledgements"), ("aging", "ageing")]:
    _add(us, gb)

# misc
for us, gb in [
    ("gray", "grey"), ("grays", "greys"), ("grayed", "greyed"), ("graying", "greying"), ("grayish", "greyish"),
    ("grayscale", "greyscale"), ("mom", "mum"), ("moms", "mums"),
    ("aluminum", "aluminium"), ("airplane", "aeroplane"), ("airplanes", "aeroplanes"), ("math", "maths"),
    ("pajamas", "pyjamas"), ("plow", "plough"), ("plows", "ploughs"), ("mold", "mould"), ("molds", "moulds"),
    ("moldy", "mouldy"), ("smolder", "smoulder"), ("smoldering", "smouldering"), ("skeptic", "sceptic"),
    ("skeptics", "sceptics"), ("skeptical", "sceptical"), ("skeptically", "sceptically"),
    ("skepticism", "scepticism"), ("maneuver", "manoeuvre"), ("maneuvers", "manoeuvres"),
    ("maneuvered", "manoeuvred"), ("maneuvering", "manoeuvring"), ("cozy", "cosy"), ("cozier", "cosier"),
    ("coziest", "cosiest"), ("mustache", "moustache"), ("woolen", "woollen"), ("sulfur", "sulphur"),
    ("omelet", "omelette"), ("tidbit", "titbit"),
]:
    _add(us, gb)

# Words that end like -ize but are spelled the same in both Englishes.
_IZE_SAME = {"size", "prize", "seize", "capsize", "maize", "baize", "assize", "belize", "bize", "brize", "frize",
             "wize", "outsize", "oversize", "undersize", "downsize", "upsize", "resize", "midsize", "fullsize",
             "lifesize", "kingsize", "queensize", "bitesize", "pintsize", "supersize", "apprize", "misprize"}

_IZE_RE = re.compile(r"^([a-z]+?)iz(e|es|ed|ing|er|ers|ation|ations|able|ational|ationally|ement|ements)$")
_YZE_RE = re.compile(r"^([a-z]+?)lyz(e|es|ed|ing|er|ers|able|ation)$")

# Proper-noun-prone entries: skip them when Title-case AND next to another Title-case word
# ("Pearl Harbor", "Color Board", "Lincoln Center", "Labor Day", "Defense Department").
_PROPER_RISK = {"center", "centers", "theater", "theaters", "color", "colors", "gray", "harbor", "labor",
                "defense", "honor", "armor", "parlor", "savior", "valor", "favor", "endeavor"}

# Protected phrases (case-sensitive substrings): never touched.
_PROTECTED_PHRASES = [
    "Center Parcs", "Final Cut Pro", "Final Cut", "Color Board", "Color Wheels", "Color Curves", "Color Inspector",
    "Color Correction", "Color Adjustments", "Hue/Saturation Curves", "Pearl Harbor", "Labor Day", "Labor Party",
    "World Health Organization", "Department of Defense", "Defense Department", "Gray's Anatomy", "Earl Grey",
    "Tom Gray", "Macy Gray", "OpenAI", "Anthropic", "Claude", "HighLevel", "GoHighLevel", "ElevenLabs",
    "Mom's Spaghetti", "Lincoln Center", "Kennedy Center", "Rockefeller Center", "Data Center World",
]

_PROTECT_RES = [
    re.compile(r"https?://\S+"),
    re.compile(r"\bwww\.\S+"),
    re.compile(r"\b[\w-]+(?:\.[\w-]+)+\.?(?:/\S*)?"),     # domains, file names, dotted identifiers (Math.round)
    re.compile(r"[@#][\w.]+"),                             # @handles, #hashtags
    re.compile(r"`[^`]*`"),                                # inline code
    re.compile(r"\{\\[^}]*\}"),                            # ASS override tags {\fs70\1c&H..&}
    re.compile(r"\b\w*[_\d]\w*\b"),                        # tokens with digits/underscores (gpt4, color_grade)
    re.compile(r"\S*[/=<>|]\S*"),                          # paths, code, markup
    re.compile(r"\\[A-Za-z]"),                              # ASS escapes (\N, \h)
]
_WORD_RE = re.compile(r"(?:(?<=\\[Nnh])|(?<![A-Za-z\\]))[A-Za-z]+")


def _british_lower(lw):
    """lowercase American word -> lowercase British word, or None."""
    if lw in _MAP:
        return _MAP[lw]
    m = _YZE_RE.match(lw)
    if m and len(m.group(1)) >= 2:
        return m.group(1) + "lys" + m.group(2)
    m = _IZE_RE.match(lw)
    if m:
        stem, suf = m.group(1), m.group(2)
        base = stem + "ize"
        if len(stem) <= 2 or base in _IZE_SAME or base.endswith(("size", "prize", "seize")):
            return None
        return stem + "is" + suf
    return None


def _match_case(src, gb):
    if src.isupper() and len(src) > 1:
        return gb.upper()
    if src[0].isupper():
        if src[1:] and not src[1:].islower():
            return None     # MiXeD case: leave it alone
        return gb[0].upper() + gb[1:]
    if not src.islower():
        return None
    return gb


def _protected_spans(text):
    spans = []
    for p in _PROTECT_RES:
        spans += [(m.start(), m.end()) for m in p.finditer(text)]
    for ph in _PROTECTED_PHRASES:
        for m in re.finditer(re.escape(ph), text):
            spans.append((m.start(), m.end()))
    return spans


def _is_title(w):
    return len(w) > 1 and w[0].isupper() and w[1:].islower()


def _replacements(text):
    """[(start, end, original, british)] for every safe change in text."""
    words = list(_WORD_RE.finditer(text))
    if not any(_british_lower(m.group(0).lower()) for m in words):
        return []
    spans = sorted(_protected_spans(text))
    starts = [a for a, _ in spans]
    # prefix max of span ends, so "is s inside any span starting at or before s" is one bisect
    reach, mx = [], -1
    for _, b in spans:
        mx = max(mx, b); reach.append(mx)

    def protected(s, e):
        k = bisect.bisect_right(starts, s) - 1
        return k >= 0 and reach[k] >= e

    out = []
    for i, m in enumerate(words):
        s, e = m.start(), m.end()
        w = m.group(0)
        if not _british_lower(w.lower()) or protected(s, e):
            continue
        # glued to an apostrophe-word on the left (e.g. the "s" of "it's") - not a word start
        if s > 0 and text[s - 1] in "'’" and s > 1 and text[s - 2].isalpha():
            continue
        if re.search(r"[a-z][A-Z]", w):     # CamelCase product names
            continue
        lw = w.lower()
        gb = _british_lower(lw)
        if not gb:
            continue
        if lw in _PROPER_RISK and _is_title(w):
            prev_w = words[i - 1].group(0) if i > 0 else ""
            next_w = words[i + 1].group(0) if i + 1 < len(words) else ""
            gap_prev = text[words[i - 1].end():s] if i > 0 else ""
            gap_next = text[e:words[i + 1].start()] if i + 1 < len(words) else ""
            near_prev = prev_w and _is_title(prev_w) and gap_prev.strip() in ("", "-") and "\n" not in gap_prev
            near_next = next_w and _is_title(next_w) and gap_next.strip() in ("", "-") and "\n" not in gap_next
            if near_prev or near_next:
                continue
        new = _match_case(w, gb)
        if new and new != w:
            out.append((s, e, w, new))
    return out


def to_british(text):
    """American -> British spelling, case/punctuation/possessives/inflections preserved."""
    if not text or not isinstance(text, str):
        return text
    reps = _replacements(text)
    if not reps:
        return text
    parts, last = [], 0
    for s, e, _, new in reps:
        parts.append(text[last:s]); parts.append(new); last = e
    parts.append(text[last:])
    return "".join(parts)


def find_americanisms(text):
    """[(found, british)] for every American spelling to_british would change."""
    return [(w, new) for _, _, w, new in _replacements(text or "")]


def normalise_words(words, key="text"):
    """Return a new list of word dicts with `key` converted to British spelling. Every other field (start, end, type,
    speaker_id, logprob...) is copied untouched. Context-aware: the words are joined (spacing items included) so the
    proper-noun guard sees neighbours."""
    out = [copy.deepcopy(w) for w in (words or [])]
    texts = [w.get(key) if isinstance(w, dict) and isinstance(w.get(key), str) else None for w in out]
    has_spacing = any(isinstance(w, dict) and w.get("type") == "spacing" for w in out)
    sep = "" if has_spacing else " "
    joined, ranges, pos = [], [], 0
    for t in texts:
        if t is None:
            ranges.append(None); continue
        if joined and sep:
            joined.append(sep); pos += len(sep)
        ranges.append((pos, pos + len(t))); joined.append(t); pos += len(t)
    full = "".join(joined)
    reps = _replacements(full)
    if not reps:
        return out
    for idx, rg in enumerate(ranges):
        if rg is None:
            continue
        a, b = rg
        mine = [r for r in reps if a <= r[0] and r[1] <= b]
        if not mine:
            continue
        t, shift = texts[idx], a
        parts, last = [], 0
        for s, e, _, new in mine:
            parts.append(t[last:s - shift]); parts.append(new); last = e - shift
        parts.append(t[last:])
        out[idx][key] = "".join(parts)
    return out


_TEXT_KEYS = {"text", "transcript", "caption", "captions", "label", "title", "subtitle", "line", "lines", "words_text",
              "on_screen_text", "hook"}


def _walk(obj, key=None):
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k == "words" and isinstance(v, list) and all(isinstance(x, dict) for x in v):
                new[k] = normalise_words(v)
            else:
                new[k] = _walk(v, k)
        return new
    if isinstance(obj, list):
        return [_walk(x, key) for x in obj]
    if isinstance(obj, str) and key in _TEXT_KEYS:
        return to_british(obj)
    return obj


def normalise_data(data):
    """Normalise a parsed transcript structure (ElevenLabs JSON: top-level "text" + "words"; or any nesting of dicts
    whose text-ish keys hold spoken words). Returns a new object."""
    return _walk(data)


def normalise_transcript_file(path_in, path_out=None):
    """Normalise an ElevenLabs JSON transcript (or a .txt/.srt/.vtt/.ass/.md text file) to British spelling.
    path_out None = rewrite path_in in place. Returns the path written. Timings are never touched."""
    raw = open(path_in, encoding="utf-8").read()
    path_out = path_out or path_in
    if path_in.lower().endswith(".json"):
        out = json.dumps(normalise_data(json.loads(raw)), ensure_ascii=False, indent=1)
    else:
        out = to_british(raw)
    with open(path_out, "w", encoding="utf-8") as f:
        f.write(out)
    return path_out


def _all_text(path, raw):
    """For --check on JSON: every converted string, joined (keeps context-guard behaviour per string)."""
    if path.lower().endswith(".json"):
        bag = []

        def walk(o, k=None):
            if isinstance(o, dict):
                if isinstance(o.get("words"), list):
                    ws = [w.get("text", "") for w in o["words"] if isinstance(w, dict)]
                    bag.append("".join(ws) if any(isinstance(w, dict) and w.get("type") == "spacing"
                                                   for w in o["words"]) else " ".join(ws))
                for kk, v in o.items():
                    if kk != "words":
                        walk(v, kk)
            elif isinstance(o, list):
                for x in o:
                    walk(x, k)
            elif isinstance(o, str) and k in _TEXT_KEYS:
                bag.append(o)
        walk(json.loads(raw))
        return "\n".join(bag)
    return raw


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="British English normaliser for captions/transcripts/on-screen text")
    ap.add_argument("path", help="file (.json/.txt/.srt/.vtt/.ass/.md) or - for stdin")
    ap.add_argument("--check", action="store_true", help="list American spellings, exit 1 if any")
    ap.add_argument("-o", "--out", help="write the normalised file here")
    ap.add_argument("--in-place", action="store_true", help="rewrite the input file")
    a = ap.parse_args(argv)
    raw = sys.stdin.read() if a.path == "-" else open(a.path, encoding="utf-8").read()
    name = a.path if a.path != "-" else "stdin.txt"
    if a.check:
        hits = find_americanisms(_all_text(name, raw))
        if not hits:
            print("british-english: clean")
            return 0
        counts = {}
        for w, gb in hits:
            counts[(w, gb)] = counts.get((w, gb), 0) + 1
        print(f"british-english: {len(hits)} American spelling(s) in {a.path}")
        for (w, gb), n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {w} -> {gb}" + (f"  (x{n})" if n > 1 else ""))
        return 1
    if name.lower().endswith(".json"):
        out = json.dumps(normalise_data(json.loads(raw)), ensure_ascii=False, indent=1)
    else:
        out = to_british(raw)
    dest = a.path if a.in_place and a.path != "-" else a.out
    if dest:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(out)
        print(dest)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
