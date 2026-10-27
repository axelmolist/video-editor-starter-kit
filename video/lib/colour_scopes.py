#!/usr/bin/env python3
"""
colour_scopes.py - Final-Cut-style video scopes + numeric readout for the colour-grader agent.

Reads a video frame (or a still image) and produces:
  1. An RGB waveform PNG that mimics Final Cut Pro's "Video Scopes" - R, G and B
     traces overlaid on a 0-100 luma % scale, with the -20..120 headroom range and a
     red 0 / 100 broadcast-safe reference line. Optionally stacks the source frame on top.
  2. A numeric readout (printed + JSON sidecar) of where each channel sits on the
     SAME 0-100 scale Final Cut Pro scopes use: floor (min / 1st pct), shadow, midtone,
     highlight (99th pct / peak) plus a skin-patch sample with the yellow-cast diagnostic.

The 0-100 scale: pixel code 0 = 0%, code 255 = 100% (full-range source, which is what
the phone / camera files here are - yuvj420p). FCP shows the same signal 0-100 with
super-black / super-white headroom drawn down to -20 and up to 120.

Usage:
  colour_scopes.py SOURCE [--t SECONDS] [--out PATH.png] [--with-frame]
                   [--skin X,Y,W,H | --skin auto] [--title "label"] [--json PATH.json]

SOURCE may be a video (a frame is extracted at --t, default middle... pass --t) or an image.
Run with the video-use venv python:
  python video/lib/colour_scopes.py ...
"""
import argparse, json, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import gridspec

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}


def extract_frame(src, t):
    """Pull one frame from a video at time t (seconds) to a temp PNG; return its path."""
    fd, png = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t}", "-i", src,
           "-frames:v", "1", png]
    subprocess.run(cmd, check=True)
    return png


def load_rgb(src, t):
    ext = os.path.splitext(src)[1].lower()
    tmp = None
    if ext in VIDEO_EXT:
        path = extract_frame(src, t if t is not None else 0)
        tmp = path
    else:
        path = src
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img)  # H x W x 3, uint8
    if tmp:
        os.unlink(tmp)
    return arr


def pct(v):
    """code value 0-255 -> 0-100 scale."""
    return float(v) / 255.0 * 100.0


def channel_stats(arr):
    """Per-channel + luma percentiles on the 0-100 scale."""
    out = {}
    names = ["R", "G", "B"]
    for i, n in enumerate(names):
        c = arr[:, :, i].ravel()
        out[n] = {
            "min": round(pct(c.min()), 1),
            "p1": round(pct(np.percentile(c, 1)), 1),
            "p10": round(pct(np.percentile(c, 10)), 1),
            "median": round(pct(np.percentile(c, 50)), 1),
            "p90": round(pct(np.percentile(c, 90)), 1),
            "p99": round(pct(np.percentile(c, 99)), 1),
            "max": round(pct(c.max()), 1),
        }
    luma = (0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]).ravel()
    out["luma"] = {
        "floor_min": round(pct(luma.min()), 1),
        "floor_p1": round(pct(np.percentile(luma, 1)), 1),
        "shadow_p10": round(pct(np.percentile(luma, 10)), 1),
        "mid_median": round(pct(np.percentile(luma, 50)), 1),
        "highlight_p90": round(pct(np.percentile(luma, 90)), 1),
        "peak_p99": round(pct(np.percentile(luma, 99)), 1),
        "peak_max": round(pct(luma.max()), 1),
    }
    return out


def skin_sample(arr, spec):
    """Return mean R,G,B for a patch. spec = 'auto' (upper-centre box) or 'X,Y,W,H'."""
    h, w, _ = arr.shape
    if spec == "auto":
        # talking-head: face tends to sit centre, upper third
        bw, bh = int(w * 0.16), int(h * 0.10)
        x = w // 2 - bw // 2
        y = int(h * 0.30)
    else:
        x, y, bw, bh = (int(v) for v in spec.split(","))
    patch = arr[y:y + bh, x:x + bw, :].reshape(-1, 3).astype(float)
    r, g, b = float(patch[:, 0].mean()), float(patch[:, 1].mean()), float(patch[:, 2].mean())
    cast = "neutral"
    if g - b > 6:
        cast = "YELLOW (G well above B - warm/jaundiced risk)"
    elif b - r > 6:
        cast = "COOL/BLUE (B above R)"
    elif r - g > 18:
        cast = "RED/MAGENTA push"
    return {
        "box": [x, y, bw, bh],
        "rgb_code": [round(r, 1), round(g, 1), round(b, 1)],
        "rgb_pct": [round(pct(r), 1), round(pct(g), 1), round(pct(b), 1)],
        "diagnostic": cast,
        "note": "Target warm-but-balanced skin: R>G>=B, G and B close. G clearly above B reads yellow.",
    }


def build_waveform(arr, cols=512, vbins=256):
    """Additive RGB waveform image (vbins tall x cols wide x 3), value 0 at bottom."""
    h, w, _ = arr.shape
    # resample columns for a clean scope; keep rows reasonable for speed
    rows = min(h, 720)
    small = np.asarray(Image.fromarray(arr).resize((cols, rows), Image.BILINEAR))
    wf = np.zeros((vbins, cols, 3), dtype=np.float64)
    col_idx = np.tile(np.arange(cols), rows)
    for c in range(3):
        vals = small[:, :, c].ravel().astype(np.int64)
        vals = np.clip(vals * (vbins - 1) // 255, 0, vbins - 1)
        np.add.at(wf[:, :, c], (vals, col_idx), 1.0)
    wf = np.log1p(wf)
    for c in range(3):
        m = wf[:, :, c].max()
        if m > 0:
            wf[:, :, c] /= m
    wf = np.flipud(wf)  # value 0 -> bottom
    return (np.clip(wf, 0, 1) * 255).astype(np.uint8)


def render(arr, wf_img, out_png, title, with_frame, skin):
    fig_w = 9
    if with_frame:
        fig = plt.figure(figsize=(fig_w, 9), facecolor="#0c0d10")
        gs = gridspec.GridSpec(2, 1, height_ratios=[1.1, 1], hspace=0.18)
        ax_im = fig.add_subplot(gs[0]); ax_im.set_facecolor("#0c0d10")
        disp = arr.copy()
        if skin:
            x, y, bw, bh = skin["box"]
            disp[y:y + 3, x:x + bw] = [255, 0, 80]; disp[y + bh - 3:y + bh, x:x + bw] = [255, 0, 80]
            disp[y:y + bh, x:x + 3] = [255, 0, 80]; disp[y:y + bh, x + bw - 3:x + bw] = [255, 0, 80]
        ax_im.imshow(disp); ax_im.axis("off")
        ax = fig.add_subplot(gs[1])
    else:
        fig = plt.figure(figsize=(fig_w, 4.4), facecolor="#0c0d10")
        ax = fig.add_subplot(111)
    ax.set_facecolor("#0c0d10")
    ax.imshow(wf_img, extent=[0, 100, 0, 100], aspect="auto", origin="upper")
    ax.set_ylim(-20, 120)
    ax.set_xlim(0, 100)
    for y in range(0, 101, 10):
        ax.axhline(y, color="#2a2d34", lw=0.6, zorder=1)
    ax.axhline(0, color="#d9455f", lw=1.0, ls="--", zorder=2)
    ax.axhline(100, color="#d9455f", lw=1.0, ls="--", zorder=2)
    ax.set_yticks(range(-20, 121, 20))
    ax.set_xticks([])
    ax.tick_params(colors="#9aa0aa", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#2a2d34")
    ax.set_ylabel("luma %  (FCP scale)", color="#9aa0aa", fontsize=9)
    if title:
        ax.set_title(title, color="#e8e9ec", fontsize=11, pad=8)
    fig.savefig(out_png, dpi=110, facecolor="#0c0d10", bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--t", type=float, default=None, help="timestamp (s) for video frame")
    ap.add_argument("--out", default=None)
    ap.add_argument("--with-frame", action="store_true", help="stack the source frame above the scope")
    ap.add_argument("--skin", default=None, help="'auto' or 'X,Y,W,H' patch to sample")
    ap.add_argument("--title", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    arr = load_rgb(args.source, args.t)
    stats = channel_stats(arr)
    skin = skin_sample(arr, args.skin) if args.skin else None
    wf = build_waveform(arr)

    base = os.path.splitext(os.path.basename(args.source))[0]
    out = args.out or f"{base}_scope.png"
    title = args.title or f"{base}" + (f" @ {args.t}s" if args.t is not None else "")
    render(arr, wf, out, title, args.with_frame, skin)

    report = {"source": args.source, "t": args.t, "scope_png": out,
              "scale": "0-100 = code 0-255 (full range); FCP shows -20..120 headroom",
              "channels": stats, "skin": skin}
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)

    L = stats["luma"]
    print(f"SCOPE -> {out}")
    print(f"  luma floor (min/p1):   {L['floor_min']} / {L['floor_p1']}   (target: above 0, ~1-2 min)")
    print(f"  shadow  p10:           {L['shadow_p10']}")
    print(f"  midtone median:        {L['mid_median']}   (target concentration ~25-40)")
    print(f"  highlight p90 / p99:   {L['highlight_p90']} / {L['peak_p99']}")
    print(f"  peak max:              {L['peak_max']}   (target: no peak above 100, cap ~80-90)")
    print(f"  R/G/B median:          {stats['R']['median']} / {stats['G']['median']} / {stats['B']['median']}")
    print(f"  R/G/B peak (p99):      {stats['R']['p99']} / {stats['G']['p99']} / {stats['B']['p99']}")
    if skin:
        print(f"  skin patch R/G/B code: {skin['rgb_code']}  -> {skin['diagnostic']}")
    if args.json:
        print(f"  json -> {args.json}")


if __name__ == "__main__":
    main()
