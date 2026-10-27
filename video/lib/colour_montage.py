#!/usr/bin/env python3
"""
colour_montage.py - tile labelled images into one grid for option-picking.

The colour-grader agent renders N preview frames (brightness options, or colour
options A/B/C/D), then calls this to lay them out as a single labelled image so the creator
can compare and pick one. Each tile carries its label (e.g. "B - cool sh / cool mid / warm hi").

Usage:
  colour_montage.py --out grid.png --cols 2 \
    "SOURCE=src.png" "A=gradeA.png" "B=gradeB.png" "C=gradeC.png"

Run with: python video/lib/colour_montage.py ...
"""
import argparse, math, os
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items", nargs="+", help='"label=path.png" entries')
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    pairs = []
    for it in args.items:
        label, path = it.split("=", 1)
        pairs.append((label, path))

    n = len(pairs)
    cols = max(1, args.cols)
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.2, rows * 4.6), facecolor="#0c0d10")
    axes = np.array(axes).reshape(-1)
    for ax in axes:
        ax.axis("off"); ax.set_facecolor("#0c0d10")
    for i, (label, path) in enumerate(pairs):
        ax = axes[i]
        if os.path.exists(path):
            ax.imshow(Image.open(path))
        ax.set_title(label, color="#e8e9ec", fontsize=10, pad=6)
    if args.title:
        fig.suptitle(args.title, color="#e8e9ec", fontsize=13, y=0.995)
    fig.savefig(args.out, dpi=110, facecolor="#0c0d10", bbox_inches="tight")
    plt.close(fig)
    print(f"MONTAGE -> {args.out}  ({n} tiles, {cols}x{rows})")


if __name__ == "__main__":
    main()
