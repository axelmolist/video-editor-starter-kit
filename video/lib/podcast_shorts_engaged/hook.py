"""The on-screen hook card: white card, ink text, ONE accent key phrase,
the configured title font, top edge on the 10% safe line, centred, inside the 80% safe width, on screen for the whole
short. Never touches the hair (the framing reads `bottom` from here).

ONE size setting, `scale` (1.0 = the reference-build v6 card: 38 px on the 1080 grid, pad 24/12, radius 16). HOOK_SCALE
below (1.30) is the default after trialling +20% and +30%; change it here and in the format standard together.
At larger sizes the text wraps to two balanced lines (never shrinks, never an orphan word, the accent phrase never
breaks). PIL here has no HarfBuzz: glyphs are unkerned, as approved on reference-build.
"""
import re
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HOOK_SCALE = 1.30
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kitconfig  # noqa: E402
FONT = kitconfig.font_file("title")     # a .ttf/.otf (or .ttc, face index 0)
_P = kitconfig.palette()
INK, ACCENT, CARD = kitconfig.hex_to_rgb(_P["background"]), kitconfig.hex_to_rgb(_P["accent"]), kitconfig.hex_to_rgb(_P["text"]) + (255,)
SAFE_W = 864            # 80% of 1080
TOP = 192               # 10% safe line (1080x1920 grid)
_EM = re.compile(r"\{(.+?)\}")


def tokens(line):
    out, pos = [], 0
    for m in _EM.finditer(line):
        out += [(w, False) for w in line[pos:m.start()].split()]
        out.append((m.group(1), True)); pos = m.end()
    out += [(w, False) for w in line[pos:].split()]
    return out


def layout(text, scale, prefer_accent=True):
    k = 38 * scale; f = ImageFont.truetype(FONT, round(k), index=0)
    padx, pady = 24 * scale, 12 * scale
    toks = tokens(text); sp = f.getlength(" ")
    width = lambda ts: sum(f.getlength(w) for w, _ in ts) + sp * (len(ts) - 1)
    if width(toks) + 2 * padx <= SAFE_W:
        lines = [toks]
    else:   # balanced 2-line split: minimise the longer line; both lines >= 2 WORDS
        best = None
        nw = lambda ts: sum(len(w.split()) for w, _ in ts)
        for i in range(1, len(toks)):
            if nw(toks[:i]) < 2 or nw(toks[i:]) < 2: continue
            a, b = toks[:i], toks[i:]
            m = max(width(a), width(b))
            if best is None or m < best[0]: best = (m, [a, b])
        lines = best[1]
        if prefer_accent:   # standard section 6: break at the accent phrase when that split fits and is <= 15% less balanced
            for i in range(1, len(toks)):
                a, b = toks[:i], toks[i:]
                if nw(a) < 2 or nw(b) < 2: continue
                if (a[-1][1] or b[0][1]) and max(width(a), width(b)) <= best[0] * 1.15 and max(width(a), width(b)) + 2 * padx <= SAFE_W:
                    lines = [a, b]; break
        assert best[0] + 2 * padx <= SAFE_W, "hook does not fit in two lines: shorten it"
    return f, lines, padx, pady, width, sp


def bottom(text, scale, prefer_accent=True):
    """card bottom row at 4K, exactly as the framing computes it (hair must clear this + margin)"""
    f, lines, padx, pady, width, sp = layout(text, scale, prefer_accent)
    a, d = f.getmetrics()
    return 2 * (TOP + (a + d) * len(lines) + 2 * pady)


def card(text, out, scale=HOOK_SCALE, prefer_accent=True):
    f1, lines, padx, pady, width, sp = layout(text, scale, prefer_accent)
    S = 2
    f = ImageFont.truetype(FONT, round(38 * scale * S), index=0)
    asc, desc = f1.getmetrics(); lh = asc + desc
    W = max(width(l) for l in lines) + 2 * padx; H = lh * len(lines) + 2 * pady
    x0, y0 = (1080 - W) / 2, TOP; r = 16 * scale
    canvas = Image.new("RGBA", (2160, 3840), (0, 0, 0, 0))
    sh = Image.new("RGBA", (2160, 3840), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([(x0 + 2) * S, (y0 + 6) * S, (x0 + W + 2) * S, (y0 + H + 6) * S], r * S, fill=(0, 0, 0, 120))
    canvas = Image.alpha_composite(canvas, sh.filter(ImageFilter.GaussianBlur(14 * S)))
    dr = ImageDraw.Draw(canvas)
    dr.rounded_rectangle([x0 * S, y0 * S, (x0 + W) * S, (y0 + H) * S], r * S, fill=CARD)
    spk = f.getlength(" ")
    for i, l in enumerate(lines):
        lw = sum(f.getlength(w) for w, _ in l) + spk * (len(l) - 1)
        x = (2160 - lw) / 2; y = (y0 + pady + i * lh) * S
        for j, (w, c) in enumerate(l):
            dr.text((x, y), w, font=f, fill=ACCENT if c else INK); x += f.getlength(w) + spk
    canvas.save(out)
    return {"png": out, "font_px_1080": round(38 * scale, 1), "font_px_4k": round(38 * scale * S), "lines": len(lines),
            "line_text": [" ".join(w for w, _ in l) for l in lines], "card_bottom_4k": round((y0 + H) * S), "card_w_1080": round(W),
            "bottom": bottom(text, scale, prefer_accent)}
