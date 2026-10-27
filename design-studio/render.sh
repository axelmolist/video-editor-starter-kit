#!/usr/bin/env bash
# design-studio render wrapper around HyperFrames.
#
#   ./render.sh still <project-dir> <out.png> [fps]
#   ./render.sh video <project-dir> <out.mp4> [fps]
#   ./render.sh alpha <project-dir> <out.mov> [fps]   # transparent video (MOV/WebM)
#
# <project-dir> contains index.html (a HyperFrames composition; see templates/).
# Needs: node 22+ (nvm use 22) and ffmpeg/ffprobe on PATH.
# Run `python3 scripts/apply_brand.py` first so brand.css and fonts-embedded.css exist.
set -euo pipefail

MODE="${1:?mode: still|video|alpha}"
PROJ="${2:?project dir}"
OUT="${3:?output path}"
FPS="${4:-25}"
mkdir -p "$(dirname "$OUT")"

case "$MODE" in
  still)
    TMP="$(mktemp -d)"
    npx --yes hyperframes render "$PROJ" --format png-sequence --fps "$FPS" -o "$TMP"
    # A still composition is one frame; grab the first frame.
    cp "$(ls "$TMP"/frame_*.png | head -1)" "$OUT"
    rm -rf "$TMP"
    ;;
  video)
    npx --yes hyperframes render "$PROJ" --format mp4 --fps "$FPS" -o "$OUT" --quality high
    ;;
  alpha)
    npx --yes hyperframes render "$PROJ" --format mov --fps "$FPS" -o "$OUT" --quality high
    ;;
  *) echo "unknown mode: $MODE" >&2; exit 2 ;;
esac

echo "wrote $OUT"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$OUT" || true
