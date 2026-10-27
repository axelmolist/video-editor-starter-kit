"""High-energy hook captions (ASS) for a podcast cold open.  ===> TEMPLATE <===

Copy it into the episode edit dir and re-time `CAPS` to the
new hook (hook-local seconds; map each spoken peak word to its time in the assembled hook),
then `python gen_hook_captions.py` writes `hook_caps.ass` next to it.

Style rules (keep these):
- Case per config/brand.json style (many channels avoid ALL CAPS in burned subtitles). Strong size contrast WITHIN a phrase (heavy emphasis word huge, connectors small).
- Plain WHITE by default. The brand accent ONLY on ~2 peak words across the whole hook
  (used SPARINGLY - e.g. the killer number). Most emphasis = big WHITE.
- Fonts by family name + Bold=0 (avoids the libass italic-fallback bug): the title font's bold
  face (big), the body font's bold face (mid), the body font (small), from config/brand.json.
- Fast fade + pop. PlayRes 3840x2160, bottom-centre (\\an2), MarginV ~400.
The CAPS below are placeholders - replace them for each episode.
"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kitconfig  # noqa: E402

_B = kitconfig.brand()
WHITE = r"&H00FFFFFF&"
ORANGE = r"&H00" + kitconfig.ass_bgr(_B["palette"]["accent"]) + "&"     # the brand accent, BBGGRR
HEAVY = _B["fonts"]["title"].get("bold_name") or _B["fonts"]["title"]["name"]
DEMI = _B["fonts"]["body"].get("bold_name") or _B["fonts"]["body"]["name"]
MED = _B["fonts"]["body"]["name"]

# kind -> (fontname, size, colour)
K = {
    "xl_o":  (HEAVY, 360, ORANGE),
    "big_o": (HEAVY, 290, ORANGE),
    "xl_w":  (HEAVY, 300, WHITE),
    "big_w": (HEAVY, 235, WHITE),
    "md_w":  (DEMI,  165, WHITE),
    "sm_w":  (MED,   125, WHITE),
}

# (start, end, [ (kind, text), ... ]) hook-local seconds
CAPS = [
    (1.00,  2.80,  [("md_w", "we tried "), ("xl_w", "everything")]),
    (3.40,  6.00,  [("xl_o", "40"), ("md_w", " different tools")]),
    (7.50,  9.60,  [("big_w", "then one "), ("xl_w", "worked")]),
]

def t(s): return f"{int(s//3600):d}:{int((s%3600)//60):02d}:{s%60:05.2f}"
def span(kind, text):
    fn, fs, col = K[kind]
    return f"{{\\fn{fn}\\fs{fs}\\1c{col}}}{text}"

head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 3840
PlayResY: 2160
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pod,{HEAVY},200,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,9,6,2,120,120,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

lines = [head]
for s, e, spans in CAPS:
    pop = r"{\fad(70,70)\fscx72\fscy72\t(0,130,\fscx100\fscy100)}"
    lines.append(f"Dialogue: 0,{t(s)},{t(e)},Pod,,0,0,0,,{pop}{''.join(span(k, x) for k, x in spans)}")
(HERE / "hook_caps.ass").write_text("\n".join(lines) + "\n")
print("wrote hook_caps.ass:", len(CAPS), "captions")
