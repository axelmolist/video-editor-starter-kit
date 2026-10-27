"""
Orientation preflight for every video that leaves this system.

Why this exists: on a short published SIDEWAYS on all five
platforms (the build-buy-wait short 4 incident). The final render carried a
QuickTime display-matrix rotation flag while its pixels were portrait
2160x3840. Every check in the pipeline looked only at width x height
("2160x3840 = portrait, fine") and file size - nothing read the rotation
flag, which is what the platforms actually use to orient playback. So the
file passed every gate and played sideways everywhere.

The rule this enforces: a FINAL render must never carry a rotation flag.
Rotation belongs baked into the pixels. Any non-identity display matrix on a
deliverable is a hard fail, full stop - and the display orientation
(after applying any rotation) must match what the destination expects
(portrait for shorts/reels).

Pure Python, no ffmpeg needed - parses the MP4/MOV boxes directly, works on a
local file OR a public URL (range requests; needs +faststart or a readable
tail), so it runs in cloud sessions and GitHub Actions too.

Usage:
    python video/lib/video_preflight.py <file-or-url> \
        [--orientation portrait|landscape|any] [--json]

    Exit 0 = safe to publish. Exit 1 = DO NOT PUBLISH (reason printed).

Fixing a flagged file (bakes the rotation into pixels, strips the flag):
    ffmpeg -i in.mp4 -c:v libx264 -b:v <same-ish> -pix_fmt yuv420p -r 25 \
        -c:a copy -movflags +faststart out.mp4
    # ffmpeg auto-rotates on re-encode; verify with this script afterwards.

Library use:
    from video_preflight import inspect_video, check
    report = inspect_video(path_or_url)
    problems = check(report, orientation="portrait")
"""
from __future__ import annotations

import argparse
import io
import json
import struct
import sys
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

FETCH_BYTES = 8 * 1024 * 1024  # head/tail window for URL probing
CONTAINER_BOXES = {"moov", "trak", "mdia", "minf", "stbl"}
VIDEO_SAMPLE_ENTRIES = {"avc1", "avc3", "hvc1", "hev1", "av01", "vp09", "mp4v"}


@dataclass
class Report:
    source: str
    size_bytes: int | None
    coded_width: int | None
    coded_height: int | None
    rotation: int | None          # degrees from the tkhd display matrix; None = no video tkhd found
    matrix_is_identity: bool | None
    display_width: int | None     # coded dims with any rotation applied - what viewers see
    display_height: int | None
    faststart: bool | None        # moov before mdat (None if undetermined)
    notes: list[str]

    @property
    def display_orientation(self) -> str | None:
        if not self.display_width or not self.display_height:
            return None
        if self.display_width == self.display_height:
            return "square"
        return "portrait" if self.display_height > self.display_width else "landscape"


def _iter_boxes(buf: bytes, start: int, end: int):
    off = start
    while off + 8 <= end:
        size, typ = struct.unpack(">I4s", buf[off:off + 8])
        hdr = 8
        if size == 1:
            if off + 16 > end:
                return
            size = struct.unpack(">Q", buf[off + 8:off + 16])[0]
            hdr = 16
        elif size == 0:  # box runs to end of file
            size = end - off
        if size < hdr:
            return
        try:
            name = typ.decode("ascii")
        except UnicodeDecodeError:
            return
        yield name, off, off + hdr, min(off + size, end)
        off += size


def _parse_tkhd(buf: bytes, body: int) -> tuple[int | None, bool, tuple[int, int]]:
    """Return (rotation_degrees_or_None, is_identity, (tkhd_disp_w, tkhd_disp_h))."""
    version = buf[body]
    # version+flags(4) then v0: 4+4+4+4+4 / v1: 8+8+4+4+8 -> then 8 reserved,
    # layer(2), alt_group(2), volume(2), reserved(2) -> matrix (9 x int32)
    matrix_off = body + (52 if version == 1 else 40)
    m = struct.unpack(">9i", buf[matrix_off:matrix_off + 36])
    w_fixed, h_fixed = struct.unpack(">II", buf[matrix_off + 36:matrix_off + 44])
    a, b, c, d = m[0] / 65536, m[1] / 65536, m[3] / 65536, m[4] / 65536
    key = (round(a), round(b), round(c), round(d))
    rot_map = {(1, 0, 0, 1): 0, (0, 1, -1, 0): 90, (-1, 0, 0, -1): 180, (0, -1, 1, 0): 270}
    rotation = rot_map.get(key)  # None = unusual (shear/scale) matrix
    return rotation, key == (1, 0, 0, 1), (w_fixed >> 16, h_fixed >> 16)


def _scan_moov(buf: bytes, report: Report) -> bool:
    """Walk boxes in buf; fill coded dims + rotation from the video track. True if a moov was parsed."""
    found = False

    def walk(start: int, end: int, inside_stsd: bool = False):
        nonlocal found
        for name, _box_start, body, box_end in _iter_boxes(buf, start, end):
            if name == "moov":
                found = True
            if name in CONTAINER_BOXES:
                walk(body, box_end)
            elif name == "stsd":
                walk(body + 8, box_end, inside_stsd=True)  # skip version/flags + entry_count
            elif name == "tkhd":
                try:
                    rotation, identity, tkhd_dims = _parse_tkhd(buf, body)
                except (struct.error, IndexError):
                    continue
                # Keep the tkhd of the VIDEO track: it is the one with non-zero
                # display dims (audio tkhd carries 0x0).
                if tkhd_dims != (0, 0):
                    report.rotation = rotation
                    report.matrix_is_identity = identity
                    if rotation is None:
                        report.notes.append(
                            f"tkhd matrix is neither identity nor a pure rotation (tkhd dims {tkhd_dims[0]}x{tkhd_dims[1]})"
                        )
            elif inside_stsd and name in VIDEO_SAMPLE_ENTRIES:
                if body + 28 <= box_end:
                    w, h = struct.unpack(">HH", buf[body + 24:body + 28])
                    report.coded_width, report.coded_height = w, h

    walk(0, len(buf))
    return found and report.coded_width is not None


def _top_level_order(buf: bytes) -> tuple[int | None, int | None]:
    moov_at = mdat_at = None
    for name, box_start, _body, _box_end in _iter_boxes(buf, 0, len(buf)):
        if name == "moov" and moov_at is None:
            moov_at = box_start
        if name == "mdat" and mdat_at is None:
            mdat_at = box_start
    return moov_at, mdat_at


def _fetch_range(url: str, spec: str) -> tuple[bytes, int | None]:
    req = urllib.request.Request(url, headers={"Range": f"bytes={spec}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = None
        crange = resp.headers.get("Content-Range", "")
        if "/" in crange and crange.split("/")[-1].isdigit():
            total = int(crange.split("/")[-1])
        return resp.read(), total


def _moov_from_tail(tail: bytes) -> bytes | None:
    """Find a plausible top-level moov box inside an arbitrary tail fragment."""
    at = 0
    while True:
        at = tail.find(b"moov", at)
        if at < 4:
            if at == -1:
                return None
            at += 4
            continue
        size = struct.unpack(">I", tail[at - 4:at])[0]
        if 8 <= size <= len(tail) - (at - 4):
            return tail[at - 4:at - 4 + size]
        at += 4


def inspect_video(source: str) -> Report:
    report = Report(source=source, size_bytes=None, coded_width=None, coded_height=None,
                    rotation=None, matrix_is_identity=None, display_width=None,
                    display_height=None, faststart=None, notes=[])

    if source.startswith(("http://", "https://")):
        head, total = _fetch_range(source, f"0-{FETCH_BYTES - 1}")
        report.size_bytes = total
        parsed = _scan_moov(head, report)
        moov_at, mdat_at = _top_level_order(head)
        if moov_at is not None and (mdat_at is None or moov_at < mdat_at):
            report.faststart = True
        elif parsed:
            report.faststart = False
        if not parsed and total and total > len(head):
            tail, _ = _fetch_range(source, f"-{FETCH_BYTES}")
            moov = _moov_from_tail(tail)
            if moov is not None:
                report.faststart = False
                report.notes.append("moov found at end of file (no +faststart)")
                _scan_moov(moov, report)
        if report.coded_width is None:
            report.notes.append("could not locate the moov/video track in the fetched ranges")
    else:
        path = Path(source).expanduser()
        buf = path.read_bytes() if path.stat().st_size <= 2 * FETCH_BYTES else None
        if buf is None:
            with path.open("rb") as fh:
                head = fh.read(FETCH_BYTES)
                fh.seek(-FETCH_BYTES, io.SEEK_END)
                tail = fh.read()
            buf = head
            report.size_bytes = path.stat().st_size
            parsed = _scan_moov(head, report)
            moov_at, mdat_at = _top_level_order(head)
            report.faststart = moov_at is not None and (mdat_at is None or moov_at < mdat_at)
            if not parsed:
                moov = _moov_from_tail(tail)
                if moov is not None:
                    report.notes.append("moov found at end of file (no +faststart)")
                    _scan_moov(moov, report)
        else:
            report.size_bytes = len(buf)
            _scan_moov(buf, report)
            moov_at, mdat_at = _top_level_order(buf)
            report.faststart = moov_at is not None and (mdat_at is None or moov_at < mdat_at)
        if report.coded_width is None:
            report.notes.append("could not parse a video track from this file (is it an MP4/MOV?)")

    if report.coded_width and report.coded_height:
        if report.rotation in (90, 270):
            report.display_width, report.display_height = report.coded_height, report.coded_width
        else:
            report.display_width, report.display_height = report.coded_width, report.coded_height
    return report


def check(report: Report, orientation: str = "portrait") -> list[str]:
    """Return the list of publish-blocking problems (empty = safe)."""
    problems: list[str] = []
    if report.coded_width is None:
        problems.append("unreadable: " + ("; ".join(report.notes) or "no video track found"))
        return problems
    if report.matrix_is_identity is None:
        problems.append("no video tkhd found - cannot verify the display matrix")
    elif not report.matrix_is_identity:
        rot = f"{report.rotation} deg" if report.rotation is not None else "a non-rotation transform"
        problems.append(
            f"ROTATION FLAG SET ({rot} display matrix). Platforms honour this and will "
            f"display the video rotated - this is exactly the sideways-short bug. "
            f"Bake the rotation into the pixels (re-encode with ffmpeg, which auto-rotates) "
            f"and re-run this check; NEVER publish a file with a rotation flag."
        )
    if orientation in ("portrait", "landscape"):
        actual = report.display_orientation
        if actual != orientation:
            problems.append(
                f"display orientation is {actual or 'unknown'} "
                f"({report.display_width}x{report.display_height} as viewers will see it) "
                f"but {orientation} was expected. If this video is genuinely {actual}, "
                f"pass --orientation {actual or 'any'} explicitly."
            )
    return problems


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Orientation/rotation preflight for a video file or URL.")
    p.add_argument("source", help="Local video file or public URL.")
    p.add_argument("--orientation", choices=["portrait", "landscape", "any"], default="portrait",
                   help="Expected DISPLAY orientation (default portrait - shorts/reels).")
    p.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = p.parse_args(argv)

    try:
        report = inspect_video(args.source)
    except Exception as exc:  # noqa: BLE001 - a probe failure must block publishing
        print(f"PREFLIGHT ERROR: could not inspect {args.source}: {exc}", file=sys.stderr)
        return 1

    problems = check(report, args.orientation)
    if args.json:
        out = asdict(report)
        out["display_orientation"] = report.display_orientation
        out["problems"] = problems
        print(json.dumps(out, indent=2))
    else:
        size = f"{report.size_bytes / 1048576:.1f} MB" if report.size_bytes else "size unknown"
        rot = "no rotation flag" if report.matrix_is_identity else f"rotation={report.rotation}"
        print(f"{args.source}")
        print(f"  coded {report.coded_width}x{report.coded_height}, {rot}, "
              f"displays as {report.display_width}x{report.display_height} "
              f"({report.display_orientation}), {size}, faststart={report.faststart}")
        for n in report.notes:
            print(f"  note: {n}")
    if problems:
        for pr in problems:
            print(f"FAIL: {pr}", file=sys.stderr)
        print("DO NOT PUBLISH this file.", file=sys.stderr)
        return 1
    print("OK: safe to publish (orientation verified).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
