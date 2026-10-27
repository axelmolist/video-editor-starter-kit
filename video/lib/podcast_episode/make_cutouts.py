"""Podcast episode - make B&W cut-outs of guest + host for the thumbnail.

Extracts a frame from each close-up, removes the background with rembg, KEEPS the
person + connected foreground props (the boom mic + the glass on the desk read as a
podcast), drops disconnected background objects (e.g. a plant), and saves grayscale
RGBA cut-outs ready for make_thumbnail.py. Pick frontal/pleasant frames (pick_frames.py).

Uses the general "u2net" salient-object model (keeps mic/glass, unlike u2net_human_seg
which strips them) + a largest-connected-component pass to drop stray background blobs.

Run with the thumb venv:
  <thumbnail venv>/bin/python make_cutouts.py \
     --episode-dir <eX> --guest-t 158 --host-t 2300 --out-dir <work>/thumb
"""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path
import numpy as np
from rembg import remove, new_session
from scipy import ndimage
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--episode-dir", required=True, type=Path)
ap.add_argument("--guest-t", required=True, type=float)
ap.add_argument("--host-t", required=True, type=float)
ap.add_argument("--out-dir", required=True, type=Path)
A = ap.parse_args()
A.out_dir.mkdir(parents=True, exist_ok=True)
sess = new_session("u2net")

def cut(src, t, name):
    raw = A.out_dir / f"{name}_raw.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t),
                    "-i", str(A.episode_dir / src), "-frames:v", "1", str(raw)], check=True)
    out = remove(Image.open(raw).convert("RGBA"), session=sess)
    arr = np.array(out)
    lbl, n = ndimage.label(arr[..., 3] > 40)
    if n > 1:                                   # keep only the person+mic+glass blob
        sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n + 1))
        keep = int(np.argmax(sizes)) + 1
        arr[..., 3] = np.where(lbl == keep, arr[..., 3], 0).astype(np.uint8)
        out = Image.fromarray(arr, "RGBA")
    a = out.split()[3]
    gray = out.convert("L").convert("RGB"); gray.putalpha(a)
    out.save(A.out_dir / f"{name}_color.png")
    gray.save(A.out_dir / f"{name}_gray.png")
    print(name, "cutout", out.size)

cut("guest-shot-4k.mov", A.guest_t, "guest")
cut("host-shot-4k.mov", A.host_t, "host")
