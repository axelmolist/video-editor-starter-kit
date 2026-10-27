"""The hook card typeset by headless Chrome (HarfBuzz shaping + kerning), opt-in per episode:
episode config "hook": {"renderer": "chrome"}. Same design and geometry as hook.py (card in the palette's text colour,
background-colour ink, ONE accent phrase, the configured title font, padding 31/16, radius 21 on the 1080 grid, top
edge on the 10% line, the same balanced two-line break preferring the accent phrase). Line breaks, line height and the
card bottom come from hook.layout(), so the framing (hair clearance) reads exactly the same `bottom` as before.

Why: a PIL build without Raqm/HarfBuzz draws glyphs unkerned, and the card reads as "collaged together". Chrome runs
with its own throwaway --user-data-dir (otherwise it hands the job to your running browser), rendered at 2x, then
LANCZOS down to the output canvas (out_scale 1.0 = 2160x3840, 0.5 = 1080x1920).
"""
import html, os, subprocess, tempfile, time
from pathlib import Path
from PIL import Image
from . import hook as HK

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _rgb(c): return f"rgb({c[0]},{c[1]},{c[2]})"


def _shot(body, out_png, out_scale):
    doc = ("<!doctype html><html><head><meta charset='utf-8'><style>"
           "html,body{margin:0;width:1080px;height:1920px;background:transparent;overflow:hidden}"
           "*{font-kerning:normal;text-rendering:geometricPrecision;-webkit-font-smoothing:antialiased}"
           "</style></head><body>" + body + "</body></html>")
    with tempfile.TemporaryDirectory() as td:
        hp = Path(td) / "t.html"; hp.write_text(doc); shot = Path(td) / "shot.png"
        p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                              f"--user-data-dir={Path(td) / 'prof'}", "--default-background-color=00000000",
                              "--force-device-scale-factor=2", "--window-size=1080,1920", f"--screenshot={shot}", hp.as_uri()],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(160):
            if shot.exists() and shot.stat().st_size > 0:
                time.sleep(0.3); break
            time.sleep(0.25)
        if p.poll() is None: p.kill()
        assert shot.exists(), "chrome screenshot failed"
        im = Image.open(shot).convert("RGBA"); assert im.size == (2160, 3840), im.size
        size = (round(2160 * out_scale), round(3840 * out_scale))
        (im if size == im.size else im.resize(size, Image.LANCZOS)).save(out_png)


def card(text, out, scale=HK.HOOK_SCALE, prefer_accent=True, out_scale=1.0):
    f1, lines, padx, pady, width, sp = HK.layout(text, scale, prefer_accent)
    asc, desc = f1.getmetrics(); lh = asc + desc
    W = max(width(l) for l in lines) + 2 * padx; H = lh * len(lines) + 2 * pady
    r = 16 * scale; px = 38 * scale
    rows = "".join("<div style='height:%dpx;line-height:%dpx;white-space:nowrap'>" % (lh, lh) + " ".join(
        f"<span style='color:{_rgb(HK.ACCENT if c else HK.INK)}'>{html.escape(w)}</span>" for w, c in l) + "</div>" for l in lines)
    body = (f"<div style='position:absolute;left:{(1080 - W) / 2:.2f}px;top:{HK.TOP}px;width:{W:.2f}px;height:{H:.2f}px;box-sizing:border-box;"
            f"padding:{pady:.2f}px 0;text-align:center;background:{_rgb(HK.CARD[:3])};border-radius:{r:.2f}px;"
            f"box-shadow:2px 6px 28px rgba(0,0,0,0.47);font-family:\"{HK.kitconfig.brand()['fonts']['title']['name']}\";font-size:{px:.2f}px'>{rows}</div>")
    _shot(body, out, out_scale)
    a = __import__("numpy").array(Image.open(out))[..., 3]
    ys = a.max(axis=1) > 230
    card_rows = [i for i, v in enumerate(ys) if v]
    return {"png": out, "renderer": "chrome", "font_px_1080": round(px, 1), "font_px_4k": round(px * 2), "lines": len(lines),
            "line_text": [" ".join(w for w, _ in l) for l in lines], "card_bottom_4k": round((HK.TOP + H) * 2), "card_w_1080": round(W),
            "measured_card_rows_out": [card_rows[0], card_rows[-1]] if card_rows else None, "out_scale": out_scale,
            "bottom": HK.bottom(text, scale, prefer_accent)}
