"""
Minimal animation primitives for the video-editor studio.

The whole point: every beat gets ONE simple, crisp primitive - the least graphic
that conveys the idea. Allowed primitives only (no bespoke many-element scenes):

  counter     - a number counting up/down
  line_graph  - a simple line drawing in, rising or falling
  pie         - a donut filling to a fraction
  bars        - 2-3 labelled bars, one optionally accent
  arrow       - A -> B, straight or gently bent, for context/cause-effect

Energy comes from SCALE + MOTION (full-screen, snappy, shake), never from adding
elements. All text is crisp and full-opacity once revealed.

Used by the animation-generator agent. Reads config through kitconfig.py.
"""
import json, math, os
from PIL import Image, ImageDraw, ImageFont

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kitconfig  # noqa: E402
CFG = kitconfig.style()


def hx(h): return kitconfig.hex_to_rgb(h)
BG, ACCENT = hx(CFG["palette"]["background"]), hx(CFG["palette"]["accent"])
TEXT, MUTE = hx(CFG["palette"]["text"]), hx(CFG["palette"]["muted"])
W, H = 1080, 1920
SS = CFG["animations"]["supersample"]; FPS = CFG["animations"]["fps"]
FONT = kitconfig.font_file("body") or CFG["captions"]["font_file"]


def S(v): return int(round(v * SS))
def fnt(px): return ImageFont.truetype(FONT, max(1, S(px)))
def c01(x): return 0.0 if x < 0 else 1.0 if x > 1 else x
def inv(t, a, b): return c01((t - a) / (b - a)) if b > a else (1.0 if t >= b else 0.0)
def lerp(a, b, t): return a + (b - a) * t
def eoc(t): t = c01(t); return 1 - (1 - t) ** 3
def eob(t): t = c01(t); c1 = 2.0; c3 = c1 + 1; return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
def eioc(t): t = c01(t); return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def text(d, x, y, s, px, col, a=255, sw=0, scol=None):
    """Crisp centred text (anchor mm). Multi-line supported. Full opacity by default."""
    f = fnt(px)
    if "\n" in s:
        asc, desc = f.getmetrics(); lh = asc + desc; lines = s.split("\n")
        for i, ln in enumerate(lines):
            yy = S(y) + (i - (len(lines) - 1) / 2) * lh
            d.text((S(x), yy), ln, font=f, fill=col + (a,), anchor="mm",
                   stroke_width=S(sw), stroke_fill=(scol or BG) + (a,))
    else:
        d.text((S(x), S(y)), s, font=f, fill=col + (a,), anchor="mm",
               stroke_width=S(sw), stroke_fill=(scol or BG) + (a,))


def shake(t, impacts, amp=20):
    sx = sy = 0.0
    for ti in impacts:
        if t >= ti:
            dt = t - ti; dec = math.exp(-dt * 22)
            sx += amp * dec * math.sin(dt * 95); sy += amp * dec * math.cos(dt * 78)
    return sx, sy


# ----------------------------- primitives -----------------------------
def counter(d, t, target, label=None, start=0.15, dur=1.0, cx=540, cy=840,
            size=220, suffix="", down=False, fmt=True):
    p = eoc(inv(t, start, start + dur))
    n = round(lerp(target, 0, p) if down else lerp(0, target, p))
    s = f"{n:,}" if fmt else str(n)
    sc = eob(inv(t, start, start + 0.4))
    text(d, cx, cy, s + suffix, int(size * min(sc, 1.12)), ACCENT, 255, sw=2)
    if label:
        text(d, cx, cy + size * 0.5, label, int(size * 0.2), TEXT,
             int(255 * eoc(inv(t, start + 0.1, start + 0.5))), sw=1)


def line_graph(d, t, values, label=None, start=0.15, dur=1.3,
               x0=250, x1=830, y_top=560, y_bot=1080):
    n = len(values); p = eoc(inv(t, start, start + dur))
    pts = [(lerp(x0, x1, i / (n - 1)), lerp(y_bot, y_top, v)) for i, v in enumerate(values)]
    d.line([S(x0 - 24), S(y_bot + 24), S(x1 + 24), S(y_bot + 24)], fill=MUTE + (110,), width=S(2))
    prog = p * (n - 1)
    for i in range(n - 1):
        seg = c01(prog - i)
        if seg <= 0: break
        ax, ay = pts[i]; bx, by = pts[i + 1]
        d.line([S(ax), S(ay), S(lerp(ax, bx, seg)), S(lerp(ay, by, seg))], fill=TEXT + (245,), width=S(6))
    if prog < n - 1:
        i = int(prog); s = prog - i
        tx, ty = lerp(pts[i][0], pts[i + 1][0], s), lerp(pts[i][1], pts[i + 1][1], s)
    else:
        tx, ty = pts[-1]
    d.ellipse([S(tx - 13), S(ty - 13), S(tx + 13), S(ty + 13)], fill=ACCENT + (255,))
    if label:
        text(d, 540, y_bot + 96, label, 40, TEXT, int(255 * eoc(inv(t, start + 0.3, start + 0.7))), sw=1)


def pie(d, t, fraction, label=None, start=0.15, dur=1.1, cx=540, cy=830, r=210, pct=True):
    p = eoc(inv(t, start, start + dur)); ang = 360 * fraction * p
    box = [S(cx - r), S(cy - r), S(cx + r), S(cy + r)]
    d.ellipse(box, outline=MUTE + (80,), width=S(16))
    if ang > 0.6:
        d.arc(box, -90, -90 + ang, fill=ACCENT + (255,), width=S(18))
    if pct:
        text(d, cx, cy, f"{round(fraction * p * 100)}%", int(r * 0.62), TEXT, 255, sw=1)
    if label:
        text(d, cx, cy + r + 78, label, 40, TEXT, int(255 * eoc(inv(t, start + 0.2, start + 0.6))), sw=1)


def bars(d, t, items, start=0.15, dur=0.9, base=1140, top=560, bw=160, gap=120, label_y=1220):
    n = len(items); tw = n * bw + (n - 1) * gap; x = 540 - tw / 2 + bw / 2
    for i, it in enumerate(items):
        lbl, frac, accent = it
        p = eioc(inv(t, start + i * 0.18, start + i * 0.18 + dur))
        bh = (base - top) * frac * p; cx = x + i * (bw + gap)
        col = ACCENT if accent else TEXT
        d.rectangle([S(cx - bw / 2), S(base - bh), S(cx + bw / 2), S(base)], fill=col + (240,))
        text(d, cx, label_y, lbl, 36, TEXT, int(255 * eoc(inv(t, start + i * 0.18 + 0.2, start + i * 0.18 + 0.6))), sw=1)


def arrow(d, t, a, b, start=0.15, bend=0, y=840, ax=300, bx=780):
    pa = eob(inv(t, start, start + 0.32)); pb = eob(inv(t, start + 0.55, start + 0.9))
    pl = eoc(inv(t, start + 0.28, start + 0.78))
    if pa > 0.02: text(d, ax, y, a, 56, TEXT, int(255 * min(pa, 1)), sw=2)
    x0, x1 = ax + 110, bx - 110
    if pl > 0.02:
        if bend == 0:
            cur = lerp(x0, x1, pl)
            d.line([S(x0), S(y), S(cur), S(y)], fill=ACCENT + (255,), width=S(7))
            hx_, hy = cur, y
        else:
            midx, midy = (x0 + x1) / 2, y - bend
            pts = []
            steps = 48
            for k in range(int(steps * pl) + 1):
                u = k / steps
                xx = (1 - u) ** 2 * x0 + 2 * (1 - u) * u * midx + u ** 2 * x1
                yy = (1 - u) ** 2 * y + 2 * (1 - u) * u * midy + u ** 2 * y
                pts.append((S(xx), S(yy)))
            if len(pts) > 1: d.line(pts, fill=ACCENT + (255,), width=S(7))
            hx_, hy = (pts[-1][0] / SS, pts[-1][1] / SS) if pts else (x0, y)
        if pl > 0.85:  # arrowhead
            d.polygon([(S(hx_), S(hy - 16)), (S(hx_ + 26), S(hy)), (S(hx_), S(hy + 16))], fill=ACCENT + (255,))
    if pb > 0.02: text(d, bx, y, b, 56, TEXT, int(255 * min(pb, 1)), sw=2)


# ----------------------------- scene builder -----------------------------
def render_scene(draw, dur, out_dir, full_screen=True, shake_impacts=(), fade_in=0.0, fade_out=0.22):
    """draw(d, t) composes primitives. Renders a crisp PNG sequence (supersampled).
    full_screen=True -> opaque background takeover. False -> transparent overlay."""
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith(".png"): os.remove(os.path.join(out_dir, f))
    n = int(round(dur * FPS))
    for fi in range(n):
        t = fi / FPS
        layer = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        draw(ImageDraw.Draw(layer), t)
        small = layer.resize((W, H), Image.LANCZOS)
        bg = Image.new("RGBA", (W, H), BG + (255,) if full_screen else (0, 0, 0, 0))
        sx, sy = shake(t, shake_impacts)
        bg.alpha_composite(small, (int(round(sx)), int(round(sy))))
        fade = (inv(t, 0, fade_in) if fade_in else 1.0) * (1 - inv(t, dur - fade_out, dur))
        if fade < 0.999:
            bg.putalpha(bg.getchannel("A").point(lambda v: int(v * fade)))
        bg.save(os.path.join(out_dir, f"{fi:04d}.png"))
    return n


# ----------------------------- demo / self-test -----------------------------
if __name__ == "__main__":
    demos = {
        "counter": lambda d, t: (text(d, 540, 360, "375,000 VIEWS", 46, MUTE, 255),
                                  counter(d, t, 375000, "ON ONE VIDEO", cy=900)),
        "line_graph": lambda d, t: (text(d, 540, 360, "BASELINE LIFTS", 46, MUTE, 255),
                                    line_graph(d, t, [0.08, 0.12, 0.95, 0.5, 0.62, 0.7], "AFTER ONE OUTLIER")),
        "pie": lambda d, t: (text(d, 540, 360, "FROM ONE VIDEO", 46, MUTE, 255),
                             pie(d, t, 0.8, "OF MY SUBS")),
        "bars": lambda d, t: (text(d, 540, 360, "PRICE VS MODEL", 46, MUTE, 255),
                              bars(d, t, [("HIGH", 0.95, False), ("LOW", 0.25, True)])),
        "arrow": lambda d, t: (text(d, 540, 360, "THE SHIFT", 46, MUTE, 255),
                               arrow(d, t, "PEOPLE", "ATTENTION", bend=120)),
    }
    out = ROOT + "/edits/_demo/verify"; os.makedirs(out, exist_ok=True)
    sheet = Image.new("RGB", (W // 3 * 5, H // 3), BG)
    for i, (nm, dr) in enumerate(demos.items()):
        layer = Image.new("RGBA", (W * SS, H * SS), BG + (255,))
        dr(ImageDraw.Draw(layer), 1.4)  # mid-animation frame
        thumb = layer.resize((W // 3, H // 3), Image.LANCZOS).convert("RGB")
        ImageDraw.Draw(thumb).text((8, 8), nm, fill=(255, 87, 87))
        sheet.paste(thumb, (i * (W // 3), 0))
    sheet.save(out + "/primitives_demo.png")
    print("demo ->", out + "/primitives_demo.png")
