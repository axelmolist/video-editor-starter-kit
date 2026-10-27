#!/bin/bash
# Example composite: scene takeovers (quick fade in/out) + captions onto the UNCUT source.
# Scenes climax on the key spoken point and clear within ~0.5s.
# Caption fontsdir must be a CLEAN font dir (only font files): libass tries to load every
# file in fontsdir and chokes on anything else. Set FONTSDIR to such a folder.
#
# usage: compose.example.sh <source.mov> <edit_dir>
#   <edit_dir>/transcripts/source.json   Scribe word-level transcript
#   <edit_dir>/renders/*.mp4             rendered scenes (see build-scenes.example.py)
set -euo pipefail
KIT="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC=$1; E=$2
FONTSDIR=${FONTSDIR:-/System/Library/Fonts}
FPS=$(python3 -c "import sys;sys.path.insert(0,'$KIT/video/lib');import kitconfig;print(kitconfig.style()['output']['fps'])")

# captions only in the talking-head gaps (outside the scene windows)
echo '[[0.2,2.1],[7.6,9.7]]' > "$E/scene_windows.json"
python3 "$KIT/video/lib/captions.py" "$SRC" "$E/transcripts/source.json" "$E/captions.ass" "$E/scene_windows.json"

FC="[1:v]format=yuva420p,fade=t=in:st=0:d=0.2:alpha=1,fade=t=out:st=1.6:d=0.3:alpha=1,setpts=PTS-STARTPTS+0.2/TB[o1];\
[2:v]format=yuva420p,fade=t=in:st=0:d=0.2:alpha=1,fade=t=out:st=1.8:d=0.3:alpha=1,setpts=PTS-STARTPTS+7.6/TB[o2];\
[0:v][o1]overlay=0:0:enable='between(t,0.2,2.1)'[a];[a][o2]overlay=0:0:enable='between(t,7.6,9.7)'[b];\
[b]subtitles=$E/captions.ass:fontsdir=$FONTSDIR[v]"

ffmpeg -y -i "$SRC" -i "$E/renders/hook.mp4" -i "$E/renders/stat.mp4" \
 -filter_complex "$FC" -map "[v]" -map 0:a \
 -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -r "$FPS" -c:a aac -b:a 256k -movflags +faststart \
 "$E/preview.mp4"
echo "composed -> $E/preview.mp4 ($(ffprobe -v error -show_entries format=duration -of default=nw=1 "$E/preview.mp4")s)"
