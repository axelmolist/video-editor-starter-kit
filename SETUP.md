# Setup

Most of setup is installing tools. Once the kit is cloned, run `claude` in the folder and it takes you through the
rest; onboarding itself takes about ten minutes.

## 0. What you need

- **macOS or Linux.** Windows through WSL2 may work, but it hasn't been tested.
- **[Claude Code](https://claude.com/claude-code)** (or Codex; both read `AGENTS.md`).
- **ffmpeg** with libass: `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Debian/Ubuntu).
- **Node.js 22**: [nodejs.org](https://nodejs.org) or `brew install node@22`.
- **Python 3.9+** with numpy and Pillow, and optionally [uv](https://docs.astral.sh/uv/).
- **An ElevenLabs account with API access** (paid) for transcription: [elevenlabs.io](https://elevenlabs.io).
- **Your fonts**, installed, with the font files to hand and the rights to use them in video.
- **Your logo** as SVG or transparent PNG, in a light and a dark version.
- Optional: **Final Cut Pro** for the project-file workflows; **Higgsfield** for generated images and video;
  **S3-compatible storage** and **Buffer** for scheduling.

## 1. Clone

```sh
git clone https://github.com/axelmolist/video-editor-starter-kit my-video-studio
cd my-video-studio
cp .env.example .env
```

If you push your copy anywhere, make it **private** once it holds your brand config.

## 2. Open it in Claude Code

```sh
claude
```

Say anything. The agent sees there's no `config/brand.json` and starts onboarding: brand and presenters, formats,
design language, palette (it can read one from your logo or website), fonts, logos, caption style, spelling, output
size and frame rate, folders, keys, animation engine and integrations. You can rerun it any time with `/setup`.

The rest of this file is what onboarding does, if you'd rather do it by hand.

## 3. Install the video-use skill

Transcription and several editing helpers come from [video-use](https://github.com/browser-use/video-use) (MIT),
installed as a Claude Code skill:

```sh
git clone https://github.com/browser-use/video-use ~/Developer/video-use
cd ~/Developer/video-use && (command -v uv >/dev/null && uv sync || pip install -e .)
mkdir -p ~/.claude/skills && ln -sfn ~/Developer/video-use ~/.claude/skills/video-use
```

Its transcriber reads `ELEVENLABS_API_KEY` from the environment or from a `.env` in the folder you run it from, so
the kit's `.env` works when the agent runs from the kit.

## 4. Remotion

```sh
cd remotion && npm install && cd ..
```

Remotion is free for individuals and small companies; larger companies need a licence
([remotion.dev/license](https://www.remotion.dev/license)). HyperFrames needs nothing installed: it runs with `npx`.

## 5. Your brand

```sh
cp config/brand.example.json config/brand.json      # then edit, or let /setup fill it
cp brand/voice.example.md brand/voice.md
python3 scripts/apply_brand.py                       # writes Remotion and CSS brand tokens
```

Caption settings are in `video/instructions/style-config.json`.

## 6. Higgsfield (optional)

For AI-generated stills or video clips, add the Higgsfield MCP server to Claude Code following Higgsfield's own
instructions, then set `generated_media.allow_ai_broll` / `allow_ai_stills` to `true` in `config/brand.json`. Both are
off by default: generated b-roll often reads as filler, and the agents prefer real footage and animation.

## 7. Check

```sh
scripts/doctor.sh
python3 video/lib/tests/test_caption_dedupe.py
python3 video/lib/tests/test_british_english.py
python3 video/lib/tests/test_kitconfig_spelling.py
cd remotion && npm run typecheck
```

Doctor prints PASS, WARN or FAIL for each item. Fix every FAIL; a WARN on something optional is fine. Once there's
no FAIL left, onboarding writes `config/.setup-complete` and the agents start taking jobs.

## 8. First job

Put a clip in `video/projects/shorts/my-first-short/raw-footage/` and tell Claude Code:
"shorts-editor, make a short from video/projects/shorts/my-first-short". You'll get a low-resolution preview to
approve before the full-resolution master.
