#!/usr/bin/env python3
"""B-roll index: probe source clips and build contact sheets for describing them.

The index master lives in video/broll-index/ (clips.csv + shots.csv, text only, in git)
and can be mirrored to a spreadsheet. Paths are relative to the library root so they stay valid
when the footage moves between drives.

  scan   <dir> [--root R] [--location local|archive] [--limit N]   probe clips, merge into clips.csv
  sheets [--only SUBSTR] [--limit N]                        build contact sheets for clips missing one
  todo   [--batch 30]                                       write batch files of clips still to describe
  apply  <batch.json>...                                    merge agent descriptions into clips/shots.csv

Two roots, both set in config/brand.json "paths": broll_library (location "local", default
video/projects) and broll_archive (location "archive", an external or network drive, optional).
The archive need not mirror the local tree; its paths are stored relative to its own root. A file
found on both keeps one row (matched by fingerprint) and gets location local+archive.

Needs Pillow (e.g. the video-use skill's venv).
"""
import argparse, csv, hashlib, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "video" / "broll-index"
CLIPS = INDEX / "clips.csv"
SHEETS_DIR = INDEX / "_contact-sheets"  # jpgs, gitignored
SHOTS = INDEX / "shots.csv"
DESC_DIR = INDEX / "_descriptions"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kitconfig  # noqa: E402
MAC_ROOT = kitconfig.path("broll_library") or REPO / "video" / "projects"
ROOTS = {"local": MAC_ROOT, "local+archive": MAC_ROOT}
if kitconfig.path("broll_archive"):
    ROOTS["archive"] = kitconfig.path("broll_archive")

VIDEO_EXT = {".mp4", ".mov", ".mxf", ".mts", ".m4v", ".insv"}
# Working files from old edits, never sources.
SKIP_DIR = re.compile(
    r"/(body_video[^/]*|[^/]*segs[^/]*|segments|renders?|build|_tmp|alt|pills|overlays|"
    r"preview[^/]*|editor-files|_review|thumb[^/]*|Proxies|Proxy Media|High Quality Media|"
    r"Render Files|Analysis Files|do-not-use)/", re.I)

# Only camera originals are indexed. Edits, exports, previews and derived shorts are not sources.
DERIVED_DIR = re.compile(
    r"(^|/)(final-footage|highlights?|[^/]*-highlight|[^/]*shorts[^/]*|project|work|rawcut_work|_tools|_shared|"
    r"assets|broll-grade|edit|sync-check|sync-verify|fcp-export|fcp-prep|full-edit|section-titles|clean|"
    r"_rejected|style-guide|screen-record[^/]*)/", re.I)
DERIVED_FILE = re.compile(
    r"export|final|rawcut|_prev|preview|review|^base\.|graded|fcp-edit|pretighten|archived|nonorm| copy|"
    r"montage|cut-v\d|hook|highlight|-full\.|vertical|nocaps|-frame\.", re.I)
PODCAST_TOP = ("podcasts/",)


def is_source(rel):
    name = rel.rsplit("/", 1)[-1]
    if rel.startswith(PODCAST_TOP):
        # Podcasts: the final exported episode only, never camera files, shorts or highlights.
        # Some episodes only have an "export" at the episode root (no FINAL file).
        if re.search(r"short|highlight|review|preview|hook|obs-", rel, re.I):
            return False
        parent = rel.split("/")[-2]
        return bool(re.search(r"final", name, re.I) or (
            re.search(r"export", name, re.I) and not re.match(r"edit|raw|fcp|clean|sync", parent, re.I)))
    parts = rel.split("/")
    if parts[0] == "shorts":
        # Standalone shorts: the raw recordings only (campaign root, raw-footage/ or rec-round-*/).
        if not (len(parts) == 3 or re.match(r"raw-footage|rec-round", parts[-2], re.I)):
            return False
        return not DERIVED_FILE.search(name)
    if DERIVED_DIR.search(rel):
        return False
    return not DERIVED_FILE.search(name)


COLUMNS = [
    "id", "path", "location", "drive_link", "tags", "description", "usable",
    "duration_s", "recorded_at", "camera", "resolution", "fps", "orientation",
    "audio", "size_bytes", "fingerprint", "contact_sheet", "notes",
]


def probe(abs_path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(abs_path)],
        capture_output=True, text=True, timeout=120)
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def fingerprint(abs_path, size):
    # Size + first/last 1 MB: cheap to compute over a slow drive, stable across renames and moves.
    h = hashlib.sha1(str(size).encode())
    with open(abs_path, "rb") as f:
        h.update(f.read(1 << 20))
        if size > 2 << 20:
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


def describe_meta(info):
    fmt = info.get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    a = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    w, h = v.get("width", 0), v.get("height", 0)
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    rot = rot or int((v.get("tags") or {}).get("rotate", 0) or 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    num, _, den = (v.get("avg_frame_rate") or "0/1").partition("/")
    fps = round(float(num) / float(den or 1), 2) if float(den or 1) else 0
    camera = " ".join(x for x in (tags.get("com.apple.quicktime.make") or tags.get("make", ""),
                                  tags.get("com.apple.quicktime.model") or tags.get("model", "")) if x)
    if not camera:
        camera = tags.get("encoder", "") if "DJI" in tags.get("encoder", "") else ""
    return {
        "duration_s": round(float(fmt.get("duration", 0) or 0), 2),
        "recorded_at": tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time", ""),
        "camera": camera,
        "resolution": f"{w}x{h}" if w else "",
        "fps": fps,
        "orientation": "portrait" if h > w else "landscape" if w else "",
        "audio": "yes" if a else "none",
    }


def load():
    if not CLIPS.exists():
        return {}
    with open(CLIPS, newline="") as f:
        return {r["path"]: r for r in csv.DictReader(f)}


def save(rows):
    INDEX.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: r["path"])
    with open(CLIPS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(ordered)


def find_videos(base):
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if not d.startswith(".") and not d.endswith(".fcpbundle")]
        for n in fn:
            p = Path(dp) / n
            if n.startswith("._") or p.suffix.lower() not in VIDEO_EXT:
                continue
            if SKIP_DIR.search(str(p) + "/"):
                continue
            yield p


def cmd_scan(a):
    root = Path(a.root).resolve()
    rows = load()
    todo = []
    known = {(r["path"], r["location"]) for r in rows.values()} | set(rows)
    for p in sorted(find_videos(Path(a.dir).resolve())):
        rel = str(p.relative_to(root))
        if is_source(rel) and rel not in known and (rel, a.location) not in known:
            todo.append((p, rel))
    if a.limit:
        todo = todo[: a.limit]

    def work(item):
        p, rel = item
        size = p.stat().st_size
        row = {c: "" for c in COLUMNS}
        row.update(describe_meta(probe(p)))
        row.update(path=rel, location=a.location, size_bytes=size, fingerprint=fingerprint(p, size))
        if not row["camera"] and p.parent.name != "raw-footage":
            row["camera"] = p.parent.name  # camera folders: sony, gopro, osmo, iphone, drone

        return row

    by_fp = {(r["size_bytes"], r["fingerprint"]): r for r in rows.values() if r.get("fingerprint")}
    dupes = 0
    with ThreadPoolExecutor(6) as ex:
        for row in ex.map(work, todo):
            twin = by_fp.get((str(row["size_bytes"]), row["fingerprint"]))
            if twin is not None:
                # Same file already indexed (other drive, or a copy on this one): keep one row.
                if twin["location"] != row["location"] and "archive" not in twin["location"]:
                    twin["location"] = "local+archive"
                where = "Archive copy" if row["location"] == "archive" else "Copy"
                twin["notes"] = "; ".join(x for x in (twin["notes"], f"{where}: {row['path']}") if x)
                dupes += 1
                continue
            key = row["path"] if row["path"] not in rows else f"ARCHIVE/{row['path']}"
            row["path"] = key
            rows[key] = row
            by_fp[(str(row["size_bytes"]), row["fingerprint"])] = row
    next_id = 1 + max((int(r["id"][1:]) for r in rows.values() if r.get("id")), default=0)
    for r in sorted(rows.values(), key=lambda r: r["path"]):
        if not r.get("id"):
            r["id"] = f"C{next_id:05d}"
            next_id += 1
    save(rows)
    print(f"scanned {len(todo)} new clips ({dupes} already indexed from the other drive); index has {len(rows)}")


def frame_times(dur):
    # One frame every ~4 s for short clips, capped at 48 frames (3 sheets of 16) for long ones.
    n = max(4, min(48, int(dur // 4) or 4))
    return [round(dur * (i + 0.5) / n, 2) for i in range(n)]


def cmd_sheets(a):
    from PIL import Image, ImageDraw, ImageFont
    rows = load()
    SHEETS_DIR.mkdir(parents=True, exist_ok=True)
    todo = [r for r in rows.values() if not r["contact_sheet"] and r["location"] in ROOTS
            and float(r["duration_s"] or 0) > 0 and (not a.only or a.only in r["path"])]
    if a.limit:
        todo = todo[: a.limit]
    try:
        font = ImageFont.truetype(next(f for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                                                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if os.path.exists(f)), 22)
    except StopIteration:
        font = ImageFont.load_default()

    def grab(src, t, portrait):
        scale = "-2:270" if portrait else "480:-2"
        r = subprocess.run(["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", "-ss", str(t), "-i", src, "-frames:v", "1",
                            "-vf", f"scale={scale}", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                           capture_output=True, timeout=120)
        from io import BytesIO
        return Image.open(BytesIO(r.stdout)).convert("RGB") if r.stdout else None

    def work(r):
        rel = r["path"][8:] if r["location"] == "archive" and r["path"].startswith("ARCHIVE/") else r["path"]
        src = str(ROOTS[r["location"]] / rel)
        times = frame_times(float(r["duration_s"] or 0))
        portrait = r["orientation"] == "portrait"
        frames = [(t, grab(src, t, portrait)) for t in times]
        frames = [(t, im) for t, im in frames if im]
        if not frames:
            return r["path"], ""
        tw, th = frames[0][1].size
        out = []
        for i in range(0, len(frames), 16):
            chunk = frames[i:i + 16]
            cols = 4 if not portrait else 8
            rws = -(-len(chunk) // cols)
            sheet = Image.new("RGB", (cols * tw, rws * th), "black")
            d = ImageDraw.Draw(sheet)
            for j, (t, im) in enumerate(chunk):
                x, y = (j % cols) * tw, (j // cols) * th
                sheet.paste(im.resize((tw, th)), (x, y))
                label = f"{int(t // 60)}:{t % 60:04.1f}"
                d.rectangle([x, y, x + 92, y + 28], fill="black")
                d.text((x + 4, y + 2), label, font=font, fill="yellow")
            name = f"{r['id']}-{i // 16 + 1}.jpg"
            sheet.save(SHEETS_DIR / name, quality=70)
            out.append(name)
        return r["path"], ";".join(out)

    done = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for path, names in ex.map(work, todo):
            rows[path]["contact_sheet"] = names
            done += 1
            if done % 25 == 0:
                save(rows)  # long runs over the slow drive: keep progress
                print(f"{done}/{len(todo)}", flush=True)
    save(rows)
    print(f"built sheets for {len(todo)} clips")


def cmd_todo(a):
    rows = load()
    DESC_DIR.mkdir(parents=True, exist_ok=True)
    # Clips already handed out (todo_*) or described (batch_*/pilot_*) are skipped, so this can
    # run again while contact sheets are still being built; new batches get the next numbers.
    taken = set()
    for f in DESC_DIR.glob("*.json"):
        try:
            taken |= {d["id"] for d in json.load(open(f))}
        except (ValueError, KeyError, TypeError):
            pass
    todo = [r for r in sorted(rows.values(), key=lambda r: r["id"])
            if not r["description"] and r["contact_sheet"] and r["id"] not in taken]
    if a.only:
        todo = [r for r in todo if a.only in r["path"]]
    start = 1 + max((int(f.stem[5:]) for f in DESC_DIR.glob("todo_*.json")), default=0)
    keep = ("id", "path", "location", "duration_s", "recorded_at", "camera", "orientation", "audio", "contact_sheet")
    for i in range(0, len(todo), a.batch):
        chunk = [{k: r[k] for k in keep} for r in todo[i:i + a.batch]]
        json.dump(chunk, open(DESC_DIR / f"todo_{start + i // a.batch:03d}.json", "w"), indent=1)
    print(f"{len(todo)} clips to describe in {-(-len(todo) // a.batch)} batches")


def cmd_apply(a):
    rows = load()
    by_id = {r["id"]: r for r in rows.values()}
    with open(SHOTS, newline="") as f:
        shots = list(csv.DictReader(f))
    n = 0
    for fn in a.files:
        for d in json.load(open(fn)):
            r = by_id.get(d["id"])
            if r is None:
                continue
            tags = d.get("tags", "")
            r["tags"] = ", ".join(tags) if isinstance(tags, list) else tags
            for k in ("description", "usable", "notes"):
                if d.get(k):
                    r[k] = d[k]
            shots = [s for s in shots if s["clip_id"] != r["id"]]
            for s in d.get("shots") or []:
                st = s.get("tags", "")
                shots.append({"clip_id": r["id"], "path": r["path"], "in": s["in"], "out": s["out"],
                              "description": s["description"], "usable": s.get("usable", "YES"),
                              "tags": ", ".join(st) if isinstance(st, list) else st})
            n += 1
    save(rows)
    shots.sort(key=lambda s: (s["clip_id"], float(s["in"])))
    with open(SHOTS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["clip_id", "path", "in", "out", "description", "tags", "usable"])
        w.writeheader()
        w.writerows(shots)
    print(f"applied {n} descriptions; shots.csv has {len(shots)} rows")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("dir")
    s.add_argument("--root", default=str(MAC_ROOT))
    s.add_argument("--location", default="local")
    s.add_argument("--limit", type=int)
    c = sub.add_parser("sheets")
    c.add_argument("--only")
    c.add_argument("--limit", type=int)
    c.add_argument("--workers", type=int, default=4)
    t = sub.add_parser("todo")
    t.add_argument("--batch", type=int, default=30)
    t.add_argument("--only")
    p = sub.add_parser("apply")
    p.add_argument("files", nargs="+")
    a = ap.parse_args()
    {"scan": cmd_scan, "sheets": cmd_sheets, "todo": cmd_todo, "apply": cmd_apply}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
