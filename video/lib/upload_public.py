"""
Upload a finished video to S3-compatible storage (DigitalOcean Spaces, AWS S3, Cloudflare R2...)
with public-read access and print its public URL.

Why this exists: schedulers that attach video by URL only (for example the Buffer MCP) download the
file from a public link and cannot ingest a local file. So a finished short must first land in a
bucket as a public object. This script does the upload + ACL + verification in one step.

Usage:
    python video/lib/upload_public.py <file> [<file> ...] \
        [--name short-3.mp4] [--date 080626] [--prefix videos]

    # defaults: --date = today (DDMMYY), --name = source filename, --prefix = videos
    # object key = {prefix}/{DDMMYY}/{name}  ->  videos/080626/short-3.mp4
    #
    # On every successful upload this also writes a sidecar JSON next to the LOCAL
    # file (same name, .json extension) logging the public URL + ffprobe metadata,
    # so a published file's URL is never lost.

Credentials (repo-root .env or environment), all required:
    SPACES_KEY       access key id
    SPACES_SECRET    secret access key
    SPACES_BUCKET    bucket name
    SPACES_REGION    region (e.g. lon1, us-east-1, auto)
    SPACES_ENDPOINT  endpoint URL (e.g. https://<region>.digitaloceanspaces.com)

Requires boto3 (pip install boto3).
"""
import argparse
import datetime as _dt
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_under_size  # noqa: E402 - sibling helper in video/lib
import video_preflight  # noqa: E402 - sibling helper in video/lib

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BUCKET = ""
DEFAULT_REGION = ""
DEFAULT_ENDPOINT = ""


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader - only sets keys not already in the environment."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _today_ddmmyy() -> str:
    now = _dt.datetime.now()
    return now.strftime("%d%m%y")


def _public_url(endpoint: str, bucket: str, key: str) -> str:
    # Spaces serves virtual-hosted style: https://{bucket}.{region}.digitaloceanspaces.com/{key}
    host = endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    return f"https://{bucket}.{host}/{key}"


def _verify_public(url: str) -> tuple[bool, str]:
    """Range-GET the first bytes; confirm 200/206 and a video/* content type."""
    req = urllib.request.Request(url, headers={"Range": "bytes=0-1023"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            ok = status in (200, 206) and ctype.startswith("video/")
            return ok, f"HTTP {status}, Content-Type {ctype or 'unknown'}"
    except Exception as exc:  # noqa: BLE001 - report any failure verbatim
        return False, f"request failed: {exc}"


def _ffprobe_meta(local: Path) -> dict:
    """Best-effort technical metadata via ffprobe. Returns {} if ffprobe is unavailable."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(local)],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(proc.stdout or "{}")
    except Exception:  # noqa: BLE001 - metadata is a nice-to-have, never fatal
        return {}
    meta: dict = {}
    fmt = data.get("format", {})
    try:
        if fmt.get("duration"):
            meta["duration_s"] = round(float(fmt["duration"]), 3)
    except (TypeError, ValueError):
        pass
    try:
        if fmt.get("size"):
            meta["size_bytes"] = int(fmt["size"])
    except (TypeError, ValueError):
        pass
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        meta["width"] = stream.get("width")
        meta["height"] = stream.get("height")
        meta["video_codec"] = stream.get("codec_name")
        rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or ""
        num, _, den = rate.partition("/")
        try:
            den_f = float(den) if den else 0.0
            if den_f:
                meta["fps"] = round(float(num) / den_f, 3)
        except ValueError:
            pass
        break
    return meta


def _write_sidecar(local: Path, *, url: str, key: str, bucket: str,
                   region: str, content_type: str, reachable: bool) -> Path:
    """Write a <video-name>.json sidecar next to the file, logging the public URL + metadata."""
    sidecar = local.with_suffix(".json")
    payload = {
        "file": local.name,
        "spaces_url": url,
        "spaces_key": key,
        "bucket": bucket,
        "region": region,
        "content_type": content_type,
        "public_reachable": reachable,
        "uploaded_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "video": _ffprobe_meta(local),
    }
    sidecar.write_text(json.dumps(payload, indent=2) + "\n")
    return sidecar


def upload_one(client, bucket, endpoint, local: Path, key: str) -> str:
    content_type = mimetypes.guess_type(local.name)[0] or "video/mp4"
    client.upload_file(
        str(local),
        bucket,
        key,
        ExtraArgs={"ACL": "public-read", "ContentType": content_type},
    )
    return _public_url(endpoint, bucket, key)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Upload video(s) to S3-compatible storage (public-read).")
    parser.add_argument("files", nargs="+", help="Local video file(s) to upload.")
    parser.add_argument("--name", help="Object filename (single file only). Default: source filename.")
    parser.add_argument("--date", help="Date folder as DDMMYY. Default: today.")
    parser.add_argument("--prefix", default="videos", help="Key prefix. Default: videos.")
    parser.add_argument("--max-mb", type=float, default=190.0,
                        help="Re-encode target if a file is over the ceiling (default 190).")
    parser.add_argument("--hard-mb", type=float, default=200.0,
                        help="Hard size ceiling; files over this are auto-shrunk before upload (default 200; provisional - taper down if size errors return).")
    parser.add_argument("--no-size-limit", action="store_true",
                        help="Upload as-is, no size check. Use ONLY when the video will not be scheduled via Buffer "
                             "(e.g. the creator said 'make this 4K, don't worry about the size').")
    parser.add_argument("--orientation", choices=["portrait", "landscape", "any"], default="portrait",
                        help="Expected DISPLAY orientation of the video(s) (default portrait - shorts/reels). "
                             "A rotation flag in the file is ALWAYS a hard fail regardless of this "
                             "(the sideways-short incident). Pass 'landscape' for genuine "
                             "landscape uploads (e.g. podcast/presentation video).")
    args = parser.parse_args(argv)

    if args.name and len(args.files) > 1:
        parser.error("--name can only be used with a single file.")

    _load_dotenv(REPO_ROOT / ".env")

    key_id = os.environ.get("SPACES_KEY")
    secret = os.environ.get("SPACES_SECRET")
    if not key_id or not secret:
        print(
            "ERROR: missing Spaces credentials. Set SPACES_KEY and SPACES_SECRET in "
            f"{REPO_ROOT / '.env'} or the environment.",
            file=sys.stderr,
        )
        return 2

    try:
        import boto3  # noqa: WPS433 - imported late so a clear message can be shown
    except ImportError:
        print("ERROR: boto3 not installed. Run: pip install boto3", file=sys.stderr)
        return 2

    bucket = os.environ.get("SPACES_BUCKET", DEFAULT_BUCKET)
    region = os.environ.get("SPACES_REGION", DEFAULT_REGION)
    endpoint = os.environ.get("SPACES_ENDPOINT", DEFAULT_ENDPOINT)
    if not (bucket and region and endpoint):
        print("ERROR: set SPACES_BUCKET, SPACES_REGION and SPACES_ENDPOINT in .env (run /setup).", file=sys.stderr)
        return 2
    date_folder = args.date or _today_ddmmyy()

    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )

    exit_code = 0
    urls = []
    for f in args.files:
        local = Path(f).expanduser()
        if not local.is_file():
            print(f"ERROR: not a file: {local}", file=sys.stderr)
            exit_code = 1
            continue
        name = args.name or local.name
        key = f"{args.prefix.strip('/')}/{date_folder}/{name}"

        # Orientation preflight (ALWAYS ON, no skip flag): a rotation flag or a
        # wrong display orientation must never reach a platform. This is the
        # guard added after the sideways-short incident - the file
        # had portrait pixels, a 90-degree display matrix, and passed every
        # size/dimension check while displaying sideways on all five platforms.
        try:
            report = video_preflight.inspect_video(str(local))
            problems = video_preflight.check(report, args.orientation)
        except Exception as exc:  # noqa: BLE001 - an unreadable file must not upload
            problems = [f"preflight could not inspect the file: {exc}"]
        if problems:
            for pr in problems:
                print(f"ERROR (preflight) {local.name}: {pr}", file=sys.stderr)
            print(f"REFUSING to upload {local.name} - fix the file and retry.", file=sys.stderr)
            exit_code = 1
            continue

        # Size gate (default ON): keep scheduled shorts under the Buffer ceiling.
        # Over the hard ceiling -> shrink to a temp file and upload that; the
        # original local file is left untouched. --no-size-limit skips this.
        upload_path = local
        tmp_fitted = None
        if not args.no_size_limit:
            size_mb = local.stat().st_size / (1024 * 1024)
            if size_mb > args.hard_mb:
                tmp_fitted = Path(tempfile.mkstemp(suffix=".mp4", dir=str(local.parent))[1])
                rc = fit_under_size.fit(local, args.max_mb, args.hard_mb, 256, tmp_fitted)
                if rc != 0:
                    print(f"ERROR: could not fit {local.name} under {args.hard_mb:.0f} MB; skipping upload.", file=sys.stderr)
                    tmp_fitted.unlink(missing_ok=True)
                    exit_code = 1
                    continue
                # Re-preflight the FITTED file: a re-encode can transpose the
                # frame when rotation metadata is mishandled.
                try:
                    fitted_report = video_preflight.inspect_video(str(tmp_fitted))
                    fitted_problems = video_preflight.check(fitted_report, args.orientation)
                except Exception as exc:  # noqa: BLE001
                    fitted_problems = [f"preflight could not inspect the fitted file: {exc}"]
                if fitted_problems:
                    for pr in fitted_problems:
                        print(f"ERROR (post-fit preflight) {local.name}: {pr}", file=sys.stderr)
                    print(f"REFUSING to upload the re-encoded {local.name} - the fit step broke it.", file=sys.stderr)
                    tmp_fitted.unlink(missing_ok=True)
                    exit_code = 1
                    continue
                upload_path = tmp_fitted
            else:
                print(f"  {local.name} is {size_mb:.1f} MB (<= {args.hard_mb:.0f} MB ceiling) - no shrink needed.", file=sys.stderr)

        try:
            url = upload_one(client, bucket, endpoint, upload_path, key)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR uploading {local}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        finally:
            if tmp_fitted is not None:
                tmp_fitted.unlink(missing_ok=True)
        ok, detail = _verify_public(url)
        status = "OK" if ok else "WARNING (not publicly reachable as video)"
        print(f"{url}", file=sys.stdout)
        print(f"  uploaded {local.name} -> {key}  [{status}: {detail}]", file=sys.stderr)
        if not ok:
            exit_code = 1
        urls.append(url)
        sidecar = _write_sidecar(
            local,
            url=url,
            key=key,
            bucket=bucket,
            region=region,
            content_type=mimetypes.guess_type(name)[0] or "video/mp4",
            reachable=ok,
        )
        print(f"  metadata sidecar -> {sidecar}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
