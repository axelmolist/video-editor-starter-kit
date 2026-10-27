"""Podcast thumbnail (1280x720) - replicates the series style:
background-colour textured bg, two B&W cut-outs bleeding off the bottom (guest left, host right),
centred 'Episode N' + big bold title, the show logo bottom-centre.

Cut-outs are made with rembg (see make_cutouts in the agent flow). The logo is
a transparent PNG of the show logo (brand/logos/).
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

ap = argparse.ArgumentParser()
ap.add_argument("--guest", required=True, type=Path)   # RGBA cutout (grayscale ok)
ap.add_argument("--host", required=True, type=Path)
ap.add_argument("--logo", required=True, type=Path)
ap.add_argument("--episode", default="Episode 1")
ap.add_argument("--title", default="The episode|title")  # '|' = line break
ap.add_argument("--out", required=True, type=Path)
A = ap.parse_args()

W, H = 1280, 720
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kitconfig  # noqa: E402
NAVY = kitconfig.hex_to_rgb(kitconfig.palette()["background"])
WHITE = kitconfig.hex_to_rgb(kitconfig.palette()["text"])
FONT = kitconfig.font_file("title")
FONT_MED = kitconfig.font_file("body") or FONT
F_BOLD, F_MED, F_HEAVY = 0, 0, 0  # face indices; set them if your font files are .ttc collections

# ---- background: vertical gradient of the brand background + centre glow + grain ----
yy = np.linspace(0, 1, H)[:, None]
top = np.clip(np.array(NAVY) * 1.8 + 6, 0, 255); bot = np.array(NAVY) * 0.7
base = (top * (1 - yy) + bot * yy)[:, None, :].repeat(W, axis=1)
xx, yg = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))
d = np.sqrt(((xx - 0.5) * 1.1) ** 2 + ((yg - 0.34) * 1.3) ** 2)
glow = np.clip(1 - d / 0.8, 0, 1)[..., None] * np.array([14, 20, 30])
arr = base + glow
rng = np.random.default_rng(7)
arr = arr + rng.normal(0, 4.5, (H, W, 1))
bg = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

def prep(path, target_h, contrast=1.18, bright=1.06):
    im = Image.open(path).convert("RGBA")
    im = im.crop(im.getbbox())                      # trim transparent margins
    rgb = im.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
    rgb = ImageEnhance.Brightness(rgb).enhance(bright)
    rgb.putalpha(im.split()[3])
    s = target_h / im.height
    return rgb.resize((int(im.width * s), target_h), Image.LANCZOS)

guest = prep(A.guest, 706)
host = prep(A.host, 726)

# place: guest bleeds off left+bottom, host off right+bottom (pushed outward so the
# centre column stays clear for the title + logo)
bg.alpha_composite(guest, (int(-guest.width * 0.28), H - guest.height + 60))
bg.alpha_composite(host, (W - int(host.width * 0.72), H - host.height + 56))

# soft dark vignette behind the logo so it always reads cleanly over any clutter
scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(scrim).ellipse([W / 2 - 280, H - 140, W / 2 + 280, H + 70], fill=(6, 11, 19, 165))
bg.alpha_composite(scrim.filter(ImageFilter.GaussianBlur(46)))

draw = ImageDraw.Draw(bg)
def centered(text, font, y, fill, track=0):
    if track == 0:
        w = draw.textlength(text, font=font)
        draw.text(((W - w) / 2, y), text, font=font, fill=fill)
    else:
        widths = [draw.textlength(c, font=font) + track for c in text]
        x = (W - (sum(widths) - track)) / 2
        for c, cw in zip(text, widths):
            draw.text((x, y), c, font=font, fill=fill)
            x += cw

# eyebrow
ep_font = ImageFont.truetype(FONT_MED, 40, index=F_MED)
centered(A.episode.upper(), ep_font, 60, WHITE, track=8)
# title (1-2 lines), bold white
title_font = ImageFont.truetype(FONT, 104, index=F_BOLD)
lines = A.title.split("|")
ty = 150
for ln in lines:
    centered(ln, title_font, ty, WHITE)
    ty += 116

# logo bottom-centre (the show's transparent logo lockup)
logo = Image.open(A.logo).convert("RGBA")
logo = logo.crop(logo.getbbox())
lw = 322; lh = int(logo.height * lw / logo.width)
logo = logo.resize((lw, lh), Image.LANCZOS)
bg.alpha_composite(logo, ((W - lw) // 2, H - lh - 28))

bg.convert("RGB").save(A.out, quality=92)
print("wrote", A.out)
