#!/usr/bin/env bash
# Checks that this machine can run the kit. PASS / WARN / FAIL per item; exits 1 on any FAIL.
# Usage: scripts/doctor.sh            (run from anywhere)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
FAILS=0; WARNS=0
pass() { printf '  PASS  %s\n' "$1"; }
warn() { printf '  WARN  %s\n' "$1"; WARNS=$((WARNS+1)); }
fail() { printf '  FAIL  %s\n' "$1"; FAILS=$((FAILS+1)); }
have() { command -v "$1" >/dev/null 2>&1; }

# Load .env without echoing it
if [ -f .env ]; then set -a; . ./.env; set +a; fi

echo "Config"
if [ -f config/brand.json ]; then
  if python3 -c "import json;json.load(open('config/brand.json'))" 2>/dev/null; then pass "config/brand.json is valid JSON"
  else fail "config/brand.json is not valid JSON"; fi
else fail "config/brand.json missing (run /setup)"; fi
[ -f .env ] && pass ".env present" || fail ".env missing (cp .env.example .env, then /setup)"
B=config/brand.json; [ -f "$B" ] || B=config/brand.example.json
cfg() { python3 -c "import json,sys;d=json.load(open('$B'));
for k in sys.argv[1].split('.'): d=d.get(k,'') if isinstance(d,dict) else ''
print(d if not isinstance(d,(list,dict)) else json.dumps(d))" "$1" 2>/dev/null; }

echo "Tools"
for t in ffmpeg ffprobe; do have $t && pass "$t ($($t -version 2>/dev/null | head -1 | cut -d' ' -f3))" || fail "$t not found (macOS: brew install ffmpeg; Debian: apt install ffmpeg)"; done
if have ffmpeg && ffmpeg -hide_banner -filters 2>/dev/null | grep -q ' subtitles '; then pass "ffmpeg has libass (subtitles filter)"
else fail "ffmpeg lacks the subtitles filter (needs libass)"; fi
if have node; then
  NV=$(node -p 'process.versions.node.split(".")[0]')
  if [ "$NV" -ge 22 ]; then pass "node $NV"; elif [ "$NV" -ge 18 ]; then warn "node $NV (Remotion ok; HyperFrames needs 22+)"; else fail "node $NV too old (need 18+, 22+ for HyperFrames)"; fi
else fail "node not found (https://nodejs.org, 22 LTS)"; fi
if have python3; then
  PV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
  python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' && pass "python3 $PV" || fail "python3 $PV too old (need 3.9+)"
  for m in numpy PIL; do python3 -c "import $m" 2>/dev/null && pass "python module $m" || warn "python module $m missing (pip install numpy pillow; or use the video-use venv)"; done
else fail "python3 not found"; fi
have uv && pass "uv" || warn "uv not found (optional, used by the video-use skill: https://docs.astral.sh/uv)"

echo "Skill and render engines"
VU=""
for d in "$HOME/.claude/skills/video-use" "${CODEX_HOME:-$HOME/.codex}/skills/video-use"; do [ -f "$d/helpers/transcribe.py" ] && VU="$d" && break; done
[ -n "$VU" ] && pass "video-use skill at $VU" || fail "video-use skill not installed (see SETUP.md step 3)"
ENGINES=$(cfg animation.engines)
if echo "$ENGINES" | grep -q remotion || [ -z "$ENGINES" ]; then
  [ -d remotion/node_modules/remotion ] && pass "remotion dependencies installed" || fail "remotion deps missing (cd remotion && npm install)"
  [ -f remotion/src/brand.generated.json ] && pass "brand tokens generated" || fail "brand tokens missing (python3 scripts/apply_brand.py)"
fi
if echo "$ENGINES" | grep -q hyperframes; then
  [ -f design-studio/brand.css ] && pass "design-studio/brand.css generated" || fail "design-studio/brand.css missing (python3 scripts/apply_brand.py)"
fi

echo "Brand assets"
for role in title body captions; do
  NAME=$(cfg fonts.$role.name); FILE=$(cfg fonts.$role.file)
  if [ -n "$FILE" ]; then
    F="$FILE"; case "$F" in /*|~*) F="${F/#\~/$HOME}";; *) F="$ROOT/$F";; esac
    [ -f "$F" ] && pass "$role font file ($NAME)" || fail "$role font file not found: $FILE"
  else
    if have fc-list && fc-list 2>/dev/null | grep -qi "$NAME"; then pass "$role font '$NAME' installed (no file path set)"
    elif [ "$(uname)" = Darwin ] && system_profiler SPFontsDataType 2>/dev/null | grep -qi "Full Name: $NAME"; then pass "$role font '$NAME' installed (no file path set)"
    else warn "$role font '$NAME': no file path in brand.json and not found by name (Python renders need the file)"; fi
  fi
done
for k in light dark; do
  L=$(cfg logos.$k); [ -n "$L" ] && [ -f "$L" ] && pass "logo ($k) $L" || warn "logo ($k) missing: ${L:-not set} (drop files in brand/logos/)"
done
[ -f brand/voice.md ] && pass "brand/voice.md" || warn "brand/voice.md missing (cp brand/voice.example.md brand/voice.md)"

echo "Keys"
if [ -n "${ELEVENLABS_API_KEY:-}" ]; then
  CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "xi-api-key: $ELEVENLABS_API_KEY" https://api.elevenlabs.io/v1/user 2>/dev/null || echo 000)
  case "$CODE" in 200) pass "ElevenLabs key valid";; 401|403) fail "ElevenLabs key rejected ($CODE)";; *) warn "ElevenLabs key not verified (HTTP $CODE; offline?)";; esac
else fail "ELEVENLABS_API_KEY not set in .env (needed for transcription)"; fi
if [ "$(cfg generated_media.allow_ai_broll)" = "True" ] || [ "$(cfg generated_media.allow_ai_stills)" = "True" ]; then
  if have claude && claude mcp list 2>/dev/null | grep -qi higgsfield; then pass "Higgsfield MCP configured"
  else warn "AI media is enabled but no Higgsfield MCP found (claude mcp list)"; fi
fi
if [ "$(cfg integrations.object_storage)" = "True" ]; then
  for v in SPACES_KEY SPACES_SECRET SPACES_BUCKET SPACES_REGION SPACES_ENDPOINT; do [ -n "${!v:-}" ] && pass "$v set" || fail "$v missing in .env"; done
  python3 -c "import boto3" 2>/dev/null && pass "boto3" || fail "boto3 missing (pip install boto3)"
fi
if [ "$(cfg integrations.buffer)" = "True" ]; then
  have claude && claude mcp list 2>/dev/null | grep -qi buffer && pass "Buffer MCP configured" || warn "Buffer enabled but no Buffer MCP found"
fi
if [ "$(cfg integrations.youtube_mcp)" = "True" ]; then
  have claude && claude mcp list 2>/dev/null | grep -qi youtube && pass "YouTube MCP configured" || warn "YouTube MCP enabled but not found"
fi

echo
echo "Result: $FAILS fail, $WARNS warn"
[ "$FAILS" -eq 0 ] || exit 1
