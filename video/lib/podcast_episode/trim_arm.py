"""Podcast episode - trim the mic BOOM ARM out of a cut-out, keeping the capsule.

The look wants just the mic capsule (+ glass), NOT the long boom arm, matching how the host
is cut. The arm is dark metal; the shirt behind/around it is bright. So we remove the arm
BY COLOUR (dark pixels) in the upper-right band - NOT by a rectangle (a box slices a square
hole in the shirt). Then we fill the few tiny holes where the arm crossed over the shirt.

Inputs a grayscale RGBA cut-out (from make_cutouts.py) and writes the trimmed one.

  --x-from   : x at/after which the arm/mount lives (≈ the capsule's right edge). Capsule
               (x < this) is untouched.
  --y-to     : y below which is the shoulder/hand (kept). Arm band is y < this.
  --dark     : luminance below this = arm metal (removed). Shirt/skin (brighter) kept.

Tune --x-from / --y-to by eyeballing the cut-out (profile alpha column heights: the arm is
the thin band). Same set each episode, so the defaults are a good starting point.

Run with the thumb venv:
  <thumbnail venv>/bin/python trim_arm.py --cutout guest_gray.png --out guest_gray.png
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("--cutout", required=True, type=Path)
ap.add_argument("--out", required=True, type=Path)
ap.add_argument("--x-from", type=int, default=1815)
ap.add_argument("--y-to", type=int, default=1585)
ap.add_argument("--dark", type=int, default=145)
A = ap.parse_args()

arr = np.array(Image.open(A.cutout).convert("RGBA"))
H, W = arr.shape[:2]
Y, X = np.mgrid[0:H, 0:W]
gray = arr[..., 0].astype(np.int32)          # cut-out is already grayscale

# 1) remove the dark boom arm/mount in the upper-right; keep bright shirt + skin hand
arm = (X >= A.x_from) & (Y < A.y_to) & (gray < A.dark) & (arr[..., 3] > 0)
arm = ndimage.binary_dilation(arm, iterations=2)   # catch the arm's edge halo
arr[..., 3] = np.where(arm, 0, arr[..., 3]).astype(np.uint8)

# 2) keep largest component (drop any orphaned arm speck)
m = arr[..., 3] > 40
lbl, n = ndimage.label(m)
if n > 1:
    sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n + 1))
    m = lbl == int(np.argmax(sizes)) + 1
    arr[..., 3] = np.where(m, arr[..., 3], 0).astype(np.uint8)

# 3) fill the tiny holes the arm left in the shirt, with the surrounding shirt tone
mask = arr[..., 3] > 40
addback = (ndimage.binary_fill_holes(mask) | ndimage.binary_closing(mask, iterations=6)) & ~mask
region = np.zeros_like(mask)
region[max(0, A.y_to - 320):A.y_to + 40, A.x_from - 60:A.x_from + 560] = True   # shirt around the arm
addback &= region
fillg = ndimage.grey_dilation(np.where(mask, gray, 0).astype(np.float32), size=25)
g = np.where(addback, fillg, gray).astype(np.uint8)
a = np.where(addback, 255, arr[..., 3]).astype(np.uint8)

Image.fromarray(np.dstack([g, g, g, a]), "RGBA").save(A.out)
print(f"trimmed arm (x>={A.x_from}, y<{A.y_to}, dark<{A.dark}); filled {int(addback.sum())}px of shirt")
