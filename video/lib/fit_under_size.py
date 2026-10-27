"""
Fit a finished video UNDER a file-size ceiling so Buffer can publish it.

Why this exists: very large video files can fail to publish through Buffer. The
main cause of the TikTok/YouTube failures was actually same-minute fan-out
collisions (stagger the schedule - see the cardinal rule in CLAUDE.md), but an
oversized file is a secondary risk, so we keep a ceiling as a safety net.

Default behaviour: every short that will be scheduled should come out <= ~190 MB
and NEVER over 200 MB. This ceiling is PROVISIONAL - if size-related publish
errors return, taper it down (200 -> 150 -> 110 -> 100) via --hard-mb/--max-mb
or by editing the defaults here and in upload_public.py. If the rendered file
is already under the ceiling, this is a no-op. If it is over, we re-encode to hit
the target - keeping 4K (2160x3840) @ 25fps and only lowering the BITRATE, which
is invisible after YouTube/TikTok re-encode on ingest anyway. Resolution is only
reduced as a genuine last resort (a very long short that cannot reach the target
at 4K without an unusable bitrate).

Override: pass --no-size-limit (or call the agents with "make this 4K, don't
worry about the size") to skip entirely and keep the original encode. Use that
only when the short will NOT be scheduled through Buffer.

Usage:
    python video/lib/fit_under_size.py <file> \
        [--target-mb 100] [--hard-mb 110] [--audio-kbps 256] \
        [--no-size-limit] [--out <path>]

    # default: edits <file> in place (only if it needs shrinking); prints the
    # final size. Exit 0 = file is now <= hard ceiling (or was already).

Requires ffmpeg + ffprobe on PATH.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MB = 1024 * 1024


def _probe(path: Path) -> dict:
    """Probe duration/size/dims AND rotation side-data. width/height here are the
    coded (pixel) dims; disp_width/disp_height are what viewers actually see once
    any display-matrix rotation is applied - always compare THOSE. (The
    'mis-transpose' was a rotation flag this probe used to be blind to.)"""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_entries",
            "format=duration,size:stream=codec_type,width,height:stream_side_data=rotation",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    dur = float(data["format"]["duration"])
    size = int(data["format"]["size"])
    w = h = None
    rotation = 0
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            w, h = s.get("width"), s.get("height")
            for sd in s.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rotation = int(sd["rotation"]) % 360
            break
    disp_w, disp_h = (h, w) if rotation in (90, 270) else (w, h)
    return {"duration": dur, "size": size, "width": w, "height": h,
            "rotation": rotation, "disp_width": disp_w, "disp_height": disp_h}


def _encode(src: Path, dst: Path, v_kbps: int, audio_kbps: int, long_edge: int | None) -> None:
    """Re-encode to a target average video bitrate. Keep 25fps. Optionally cap the
    long edge (last-resort downscale); by default resolution is untouched."""
    vf = []
    if long_edge is not None:
        # vertical: long edge is height. scale height, keep aspect, even dims.
        vf = ["-vf", f"scale=-2:{long_edge}"]
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        *vf,
        "-c:v", "libx264",
        "-b:v", f"{v_kbps}k",
        "-maxrate", f"{int(v_kbps * 1.3)}k",
        "-bufsize", f"{int(v_kbps * 2)}k",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-r", "25",
        "-c:a", "aac", "-b:a", f"{audio_kbps}k",
        "-movflags", "+faststart",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _target_video_kbps(target_mb: float, duration: float, audio_kbps: int, safety: float) -> int:
    total_kbps = (target_mb * 8 * 1024 * safety) / duration  # kbit/s
    v = int(total_kbps - audio_kbps)
    return max(v, 1000)  # never below 1 Mbps video


def fit(path: Path, target_mb: float, hard_mb: float, audio_kbps: int, out: Path | None) -> int:
    info = _probe(path)
    size_mb = info["size"] / MB
    if size_mb <= hard_mb:
        # Already safe. (We use the HARD ceiling as the no-op gate so we never
        # re-encode a file that is, say, 103 MB and already publishable.)
        if info["rotation"]:
            print(
                f"WARNING: {path.name} carries a {info['rotation']}-degree ROTATION FLAG "
                f"(coded {info['width']}x{info['height']}, displays "
                f"{info['disp_width']}x{info['disp_height']}). Platforms will show it rotated - "
                f"this is the sideways-short bug. Fix it BEFORE scheduling "
                f"(upload_public.py will refuse it); check with lib/video_preflight.py.",
                file=sys.stderr,
            )
        print(f"OK: {path.name} is {size_mb:.1f} MB (<= {hard_mb:.0f} MB ceiling) - no re-encode needed.")
        return 0

    dur = info["duration"]
    if info["rotation"]:
        print(
            f"NOTE: {path.name} carries a {info['rotation']}-degree rotation flag "
            f"(coded {info['width']}x{info['height']}, displays {info['disp_width']}x{info['disp_height']}). "
            f"The re-encode will bake the rotation into the pixels and strip the flag - "
            f"the display orientation is verified after each attempt.",
            file=sys.stderr,
        )
    print(
        f"{path.name} is {size_mb:.1f} MB (> {hard_mb:.0f} MB) - re-encoding to ~{target_mb:.0f} MB "
        f"at {info['width']}x{info['height']} (duration {dur:.1f}s)."
    )

    dst_final = out or path
    # Attempt 1: keep resolution, target the ceiling. Attempt 2: tighter target.
    # Attempt 3+: last-resort downscale long edge.
    plans = [
        (target_mb, 0.95, None),
        (target_mb, 0.85, None),
        (target_mb, 0.90, 2560),
        (target_mb, 0.90, 1920),
    ]
    for target, safety, long_edge in plans:
        v_kbps = _target_video_kbps(target, dur, audio_kbps, safety)
        tmp = Path(tempfile.mkstemp(suffix=".mp4", dir=str(dst_final.parent))[1])
        try:
            _encode(path, tmp, v_kbps, audio_kbps, long_edge)
            # ORIENTATION GUARD (BLOCKING): the output must DISPLAY the same way
            # the input displayed. On a rotation flag on the source
            # made a re-encode here come out transposed, and the sideways file
            # published to all five platforms on 15 Jul. Never ship a flipped fit.
            out_info = _probe(tmp)
            if out_info["rotation"] != 0:
                tmp.unlink(missing_ok=True)
                print(
                    f"ERROR: re-encode left a {out_info['rotation']}-degree rotation flag on the "
                    f"output - refusing to use it. Bake the rotation out of the SOURCE first.",
                    file=sys.stderr,
                )
                return 3
            if long_edge is None and (out_info["disp_width"], out_info["disp_height"]) != (
                info["disp_width"], info["disp_height"],
            ):
                tmp.unlink(missing_ok=True)
                print(
                    f"ERROR: re-encode changed the display geometry - input displays "
                    f"{info['disp_width']}x{info['disp_height']}, output displays "
                    f"{out_info['disp_width']}x{out_info['disp_height']}. Refusing to use it. "
                    f"(This is the transpose failure - check the source's rotation "
                    f"metadata with lib/video_preflight.py.)",
                    file=sys.stderr,
                )
                return 3
            if long_edge is not None:
                in_portrait = info["disp_height"] > info["disp_width"]
                out_portrait = out_info["disp_height"] > out_info["disp_width"]
                if in_portrait != out_portrait:
                    tmp.unlink(missing_ok=True)
                    print(
                        f"ERROR: downscale flipped the orientation (input displays "
                        f"{info['disp_width']}x{info['disp_height']}, output "
                        f"{out_info['disp_width']}x{out_info['disp_height']}). Refusing to use it.",
                        file=sys.stderr,
                    )
                    return 3
            new_mb = tmp.stat().st_size / MB
            if new_mb <= hard_mb:
                shutil.move(str(tmp), str(dst_final))
                res_note = "4K kept" if long_edge is None else f"downscaled long edge -> {long_edge}"
                print(
                    f"DONE: {dst_final.name} now {new_mb:.1f} MB "
                    f"(video ~{v_kbps} kbps, {res_note})."
                )
                if long_edge is not None:
                    print(
                        "  NOTE: had to drop below 4K to fit - this short was too long to "
                        "stay 2160x3840 under the ceiling. Mention this to the creator.",
                        file=sys.stderr,
                    )
                return 0
            tmp.unlink(missing_ok=True)
            print(f"  attempt landed {new_mb:.1f} MB, still over - tightening.", file=sys.stderr)
        except subprocess.CalledProcessError as exc:
            tmp.unlink(missing_ok=True)
            print(f"ERROR: ffmpeg failed: {exc.stderr[-500:] if exc.stderr else exc}", file=sys.stderr)
            return 2

    print("ERROR: could not get the file under the ceiling even after downscaling.", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Fit a video under a file-size ceiling for Buffer scheduling.")
    p.add_argument("file", help="Video file to check / shrink.")
    p.add_argument("--target-mb", type=float, default=190.0, help="Re-encode target size (default 190).")
    p.add_argument("--hard-mb", type=float, default=200.0, help="Hard ceiling; files at/under this are left alone (default 200; provisional - taper down if size errors return).")
    p.add_argument("--audio-kbps", type=int, default=256, help="Audio bitrate for re-encode (default 256).")
    p.add_argument("--no-size-limit", action="store_true", help="Skip entirely; keep the original encode (use only when NOT scheduling via Buffer).")
    p.add_argument("--out", help="Write fitted file here instead of editing in place.")
    args = p.parse_args(argv)

    src = Path(args.file).expanduser()
    if not src.is_file():
        print(f"ERROR: not a file: {src}", file=sys.stderr)
        return 2

    if args.no_size_limit:
        print(f"--no-size-limit: leaving {src.name} untouched (will not be size-checked).")
        return 0

    out = Path(args.out).expanduser() if args.out else None
    return fit(src, args.target_mb, args.hard_mb, args.audio_kbps, out)


if __name__ == "__main__":
    raise SystemExit(main())
