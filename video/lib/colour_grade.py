#!/usr/bin/env python3
"""
colour_grade.py - apply a grade the way a Final Cut colourist would, and print the exact values.

Two stages, mirroring a Final Cut Color Wheels routine:

  BRIGHTNESS (a master tone curve, expressed on the 0-100 scope scale editors read):
    --floor    raise the darkest point off 0 so nothing is crushed   (default 2)
    --mid      where the midtone mass should concentrate ~25-40       (default 33)
    --ceiling  cap the brightest point so nothing peaks over 100      (default 80)
    These become a 4-point ffmpeg `curves` master: 0/floor, 0.4/mid, 0.85/(ceiling-headroom), 1/ceiling.

  COLOUR (per-tonal-range balance + global saturation), via ffmpeg `colorbalance` + `eq`:
    Named presets matching the looks most often chosen between -
      A  cool-sh warm-mid warm-hi   (split tone, warm skin)
      B  cool-sh cool-mid warm-hi   (the house look)
      C  cool-everything            (clean/cold)
      D  warm-everything            (golden)
    Each preset's magnitudes are tunable with --strength (0..2, default 1) and individual
    overrides (--rs/--gs/--bs shadows, --rm/--gm/--bm mids, --rh/--gh/--bh highlights).
    --sat global saturation (default 1.1, a common starting point).

Render targets:
    (default)  one frame at --t -> a fast PNG preview (use for option-picking)
    --full     the whole video -> a graded mp4 (use once levels + colour are chosen)

Always prints, and writes a .json sidecar of, the EXACT values + the ffmpeg filter string,
so the chosen recipe can be baked into a cut's per-segment vf or saved to style-config.json.

Run with any python3 that can see ffmpeg on PATH:
  python video/lib/colour_grade.py SOURCE [opts]
"""
import argparse, json, os, subprocess, sys

PRESETS = {
    # rs gs bs | rm gm bm | rh gh bh  (colorbalance, -1..1; small numbers)
    "A": dict(rs=-0.02, gs=0.00, bs=0.06,  rm=0.04, gm=0.01, bm=-0.02,  rh=0.05, gh=0.01, bh=-0.02),
    "B": dict(rs=-0.02, gs=0.00, bs=0.06,  rm=-0.01, gm=-0.01, bm=0.05,  rh=0.03, gh=0.00, bh=-0.02),
    "C": dict(rs=-0.03, gs=0.00, bs=0.07,  rm=-0.02, gm=0.00, bm=0.05,  rh=-0.02, gh=0.00, bh=0.05),
    "D": dict(rs=0.04, gs=0.01, bs=-0.03,  rm=0.04, gm=0.01, bm=-0.03,  rh=0.05, gh=0.01, bh=-0.03),
}
PRESET_LABEL = {
    "A": "cool shadows / warm mids / warm highs",
    "B": "cool shadows / cool mids / warm highs  (house look)",
    "C": "cool shadows / cool mids / cool highs  (clean/cold)",
    "D": "warm everywhere  (golden)",
}


def build_curve(floor, mid, ceiling, mid_in, ceil_in):
    """0-100 scope targets -> ffmpeg curves master (0-1 control points).

    mid_in  = the INPUT level (scope %) the footage's midtone mass currently sits at,
              which we want lifted/pushed to `mid`. Read it off the source scope first.
    ceil_in = the INPUT level the current peak sits at, mapped down to `ceiling`.
    Anchoring to measured input positions is what makes the result hit the target on the scope."""
    f = floor / 100.0
    mi, mo = mid_in / 100.0, mid / 100.0
    ci, co = ceil_in / 100.0, ceiling / 100.0
    # keep control points strictly increasing in input
    mi = min(max(mi, 0.08), 0.7)
    ci = min(max(ci, mi + 0.1), 1.0)
    pts = f"0/{f:.4f} {mi:.3f}/{mo:.4f} {ci:.3f}/{co:.4f}"
    if ci < 0.999:
        pts += f" 1/{min(co + 0.02, 1.0):.4f}"
    return pts


def build_filter(curve_pts, cb, sat):
    cbstr = ("colorbalance="
             f"rs={cb['rs']:.4f}:gs={cb['gs']:.4f}:bs={cb['bs']:.4f}:"
             f"rm={cb['rm']:.4f}:gm={cb['gm']:.4f}:bm={cb['bm']:.4f}:"
             f"rh={cb['rh']:.4f}:gh={cb['gh']:.4f}:bh={cb['bh']:.4f}")
    return f"curves=master='{curve_pts}',{cbstr},eq=saturation={sat:.3f}"


def render_frame(src, t, vf, out_png):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t}", "-i", src,
           "-frames:v", "1", "-vf", vf, out_png]
    subprocess.run(cmd, check=True)


def render_full(src, vf, out_mp4):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
           "-vf", vf, "-c:v", "libx264", "-crf", "17", "-preset", "medium",
           "-pix_fmt", "yuv420p", "-c:a", "copy", out_mp4]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--preset", default="B", choices=list(PRESETS))
    ap.add_argument("--strength", type=float, default=1.0, help="scale preset colour magnitudes")
    ap.add_argument("--floor", type=float, default=2.0)
    ap.add_argument("--mid", type=float, default=33.0)
    ap.add_argument("--ceiling", type=float, default=80.0)
    ap.add_argument("--mid-in", dest="mid_in", type=float, default=40.0,
                    help="input scope %% where the footage's mids currently sit (read from source scope)")
    ap.add_argument("--ceil-in", dest="ceil_in", type=float, default=100.0,
                    help="input scope %% where the current peak sits (read from source scope p99/max)")
    ap.add_argument("--sat", type=float, default=1.10)
    for k in ("rs", "gs", "bs", "rm", "gm", "bm", "rh", "gh", "bh"):
        ap.add_argument(f"--{k}", type=float, default=None, help="override colorbalance channel")
    ap.add_argument("--t", type=float, default=0.0, help="frame timestamp for preview")
    ap.add_argument("--full", action="store_true", help="render the whole video, not a preview frame")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--label", default=None, help="title text baked into nothing - just for the printout")
    args = ap.parse_args()

    cb = {k: v * args.strength for k, v in PRESETS[args.preset].items()}
    for k in cb:
        ov = getattr(args, k)
        if ov is not None:
            cb[k] = ov
    curve = build_curve(args.floor, args.mid, args.ceiling, args.mid_in, args.ceil_in)
    vf = build_filter(curve, cb, args.sat)

    base = os.path.splitext(os.path.basename(args.source))[0]
    if args.full:
        out = args.out or f"{base}_graded.mp4"
        render_full(args.source, vf, out)
    else:
        out = args.out or f"{base}_grade_{args.preset}.png"
        render_frame(args.source, args.t, vf, out)

    recipe = {
        "source": args.source, "output": out, "full_render": args.full,
        "preset": args.preset, "preset_label": PRESET_LABEL[args.preset],
        "strength": args.strength,
        "brightness_scope_targets": {"floor": args.floor, "mid": args.mid, "ceiling": args.ceiling,
                                     "mid_in": args.mid_in, "ceil_in": args.ceil_in},
        "curve_master_points": curve,
        "colorbalance": {k: round(v, 4) for k, v in cb.items()},
        "saturation": args.sat,
        "ffmpeg_vf": vf,
    }
    if args.json:
        with open(args.json, "w") as f:
            json.dump(recipe, f, indent=2)

    lbl = args.label or PRESET_LABEL[args.preset]
    print(f"GRADE [{args.preset}] {lbl}")
    print(f"  output -> {out}")
    print(f"  brightness  floor={args.floor}  mid={args.mid}  ceiling={args.ceiling}  (scope %)")
    print(f"  curve       master='{curve}'")
    print(f"  shadows     R{cb['rs']:+.3f} G{cb['gs']:+.3f} B{cb['bs']:+.3f}")
    print(f"  midtones    R{cb['rm']:+.3f} G{cb['gm']:+.3f} B{cb['bm']:+.3f}")
    print(f"  highlights  R{cb['rh']:+.3f} G{cb['gh']:+.3f} B{cb['bh']:+.3f}")
    print(f"  saturation  {args.sat}")
    print(f"  ffmpeg vf   {vf}")
    if args.json:
        print(f"  json -> {args.json}")


if __name__ == "__main__":
    main()
