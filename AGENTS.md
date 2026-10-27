# Video editor starter kit - operating instructions

> **This file is the single source of truth and it is tool-agnostic.** `CLAUDE.md` is a symlink to this file, so
> Claude Code and Codex read the same instructions. Edit `AGENTS.md`. Never replace the symlink with a copy.

This repo turns raw footage into finished videos with an AI coding agent: YouTube long-form, podcast episodes,
podcast shorts, solo shorts, vlogs, animations and motion graphics, colour grading and captions. The agents in
`.claude/agents/` do the work; the method lives in `video/instructions/` and `guides/`; the code lives in
`video/lib/`, `remotion/` and `design-studio/`.

## First run: onboarding comes before anything else (BLOCKING)

**If `config/brand.json` does not exist, or `config/.setup-complete` does not exist, run the onboarding below
before doing any other task**, whatever the user asked. Say in one line why ("this kit needs your brand and keys
first; it takes about ten minutes"). The user can rerun it any time with `/setup`.

### Onboarding

Ask a few questions at a time (never a wall of twenty). Offer sensible defaults. Write answers as you go, so a
half-finished setup is not lost. **Secrets go only in `.env`, never in `config/` or any committed file.**

1. **Who.** Brand or channel name; presenter name(s) and roles (host, co-host); website. -> `config/brand.json`
   `brand_name`, `presenters`, `website`.
2. **Formats.** Which do they make: YouTube long-form, podcast episodes, podcast shorts, solo shorts, vlog? ->
   `formats`.
3. **Design language.** In their own words: how should the videos feel? Ask for reference links or images (their own
   past videos, channels they admire). Save images in `brand/references/`. -> `design_language`, `references`.
4. **Colour palette.** Hex values for `background`, `primary`, `accent`, `text`, `muted` (and optional `extras`).
   Offer to derive them: from a logo file (sample its dominant colours with Pillow), or from their website (fetch the
   CSS and read the custom properties / most-used colours). Show the proposed palette as a small swatch PNG and
   confirm. Check contrast: `text` on `background` should be clearly readable. -> `palette`.
5. **Fonts.** Title, body and caption fonts. Confirm each is installed locally (`fc-list | grep -i <name>` or, on
   macOS, `system_profiler SPFontsDataType`) and ask for the font FILE paths (`.otf`/`.ttf`; a `.ttc` collection works
   for most tools but cannot be embedded in HTML). Ask for the bold face's exact name and file too. **Licence
   warning:** only use fonts they are licensed to use in video; free options are Inter, Manrope, DM Sans and others
   from Google Fonts. Explain the gotcha once: HTML renderers (HyperFrames) silently fall back to a serif if a font is
   loaded with `url(file://...)`, so this kit embeds fonts as data URIs. -> `fonts`.
6. **Logos.** Ask them to drop logo files into `brand/logos/` (SVG or transparent PNG): a light version (for dark
   backgrounds), a dark version, and optionally a mark/icon. -> `logos`.
7. **Captions.** Case (as spoken / upper / lower), position (lower third / centre), words per cue (1-2 for punchy,
   3-4 for calm), outline (always / adaptive / never), highlight colour (default: the accent), any words to always
   highlight. -> `video/instructions/style-config.json` `captions`.
8. **Spelling and voice.** Spelling locale (`en-GB` British, `en-US` American, `en-AU`...). Names Scribe is likely to
   mishear (their name, product names, guests' companies) with correct spellings. Rules for on-screen text (dashes,
   case, topics never shown on screen, e.g. revenue). -> `locale` in `config/brand.json`; the rest into
   `brand/voice.md` (copy it from `brand/voice.example.md`).
9. **Output.** Resolution and frame rate they shoot and deliver (default 4K at 25 fps; 24, 30 and 60 are fine).
   Footage in at a resolution and fps goes out at the same. -> `output`.
10. **Where things live.** Raw footage folder, b-roll library (and an optional archive drive), music and SFX folders.
    Defaults are inside `video/`. -> `paths`.
11. **Transcription: ElevenLabs.** The kit transcribes with ElevenLabs Scribe (word-level timestamps). They need a
    paid ElevenLabs account and an API key from elevenlabs.io (Settings -> API keys). -> `.env`
    `ELEVENLABS_API_KEY`.
12. **Generated media: Higgsfield (optional).** For AI-generated stills or video clips. It connects as an MCP server
    (see SETUP.md). Ask whether they want AI-generated b-roll at all: many creators ban it because it reads as filler.
    -> `generated_media.allow_ai_broll`, `allow_ai_stills`; key in `.env` if they use the API.
13. **Animation engine.** Remotion (React, the default, best for motion graphics; free for individuals and small
    companies, a paid company licence above that size, see remotion.dev/license) and/or HyperFrames (HTML/CSS, good
    for stills and simple animation). -> `animation.engines`, `default_engine`.
14. **Optional integrations.** Buffer (scheduling, needs public video URLs), YouTube MCP (channel data, uploads),
    S3-compatible storage such as DigitalOcean Spaces or Cloudflare R2 (for public video URLs). Only set up what they
    want. -> `integrations`; secrets in `.env`.
15. **Export approval.** Should agents always wait for an explicit "go" before rendering a final video file? Default
    yes. -> `export_approval`.

Then:
- Copy `config/brand.example.json` to `config/brand.json` if not done, and make sure every field is filled.
- Run `python3 scripts/apply_brand.py` (writes the Remotion and CSS brand tokens).
- Install the **video-use** skill if it is missing (see SETUP.md), then `cd remotion && npm install`.
- Run `scripts/doctor.sh`. Fix every FAIL with the user. WARN is acceptable for optional items.
- Render one proof: `cd remotion && npx remotion still TitleCard ../video/working-material/brand-proof.png --frame=60` and show it.
  Ask "does this look like you?" and adjust palette or fonts until it does.
- Only when doctor has no FAIL: write the date to `config/.setup-complete`.

## Layout

```
config/                 brand.json (yours, gitignored), brand.example.json, .setup-complete
brand/                  logos/, references/, voice.md (spelling patch, naming, on-screen rules)
video/instructions/     style-config.json (how videos are built), guardrails, per-format specs
video/lib/              Python tools: captions, cuts, colour, b-roll index, podcast shorts toolchain, vlog tools
video/projects/         your projects, one folder per video: raw-footage/, editor-files/, final-footage/
video/working-material/ music/, sfx/, style-references/
remotion/               Remotion project: brand kit, examples, per-video jobs
design-studio/          HTML/CSS (HyperFrames) stills and animation
guides/                 craft guides: short-form standard, retention, hook frame counting
scripts/                apply_brand.py, doctor.sh
.claude/agents/         the agents; .claude/commands/setup.md is /setup
```

## Agents

| Agent | Job |
|---|---|
| `video-editor` | Front door: routes requests; adds captions + graphics to a finished cut |
| `youtube-long-editor` | Solo long-form from a raw take to a finished video or FCPXML |
| `podcast-editor` | Multicam podcast episode, hook, thumbnail, packaging |
| `podcast-shorts` | Vertical (and landscape highlight) shorts from a podcast episode |
| `shorts-editor` | Solo vertical shorts, clean or dynamic |
| `youtube-vlog` | Vlog planning and editing, spine first |
| `animation-locator` -> `diagram-designer` -> `animation-generator` | The animation pipeline |
| `colour-grader` | Options-first grading; builds the house look |

## Hard rules

1. **Brand values come from `config/brand.json` only.** Never hard-code a colour, font or name in code or in an
   agent. Change config, rerun `scripts/apply_brand.py`.
2. **Secrets only in `.env`.** Never print a key, never commit one.
3. **Export approval.** When `export_approval` is true, never render a final video, upload or schedule without the
   creator's explicit go-ahead for that file. Stills, project files, audio and analysis are always allowed.
4. **Never overwrite a render.** Every render gets a new `-vN`.
5. **Cut points come from the audio, never from transcript timestamps.** Scribe inflates word ends.
6. **Never eat into speech.** Protect quiet onsets and trailing consonants; if unsure, keep the audio.
7. **Resolution and fps in = out.** Verify every render with ffprobe.
8. **No invented facts on screen.** Numbers, names and quotes only as spoken or from a verified source.
9. **Spelling in the configured locale** (`video/lib/spelling.py`) and **no caption echo**
   (`video/lib/caption_dedupe.py`) on every video.
10. **Phone safe zone** on every vertical video: overlays inside x 14%-86%, nothing above 12%.
11. **Projects stay out of git.** `video/projects/` and media are gitignored; this repo holds method and code.

## Third-party tools

- **video-use** (MIT, github.com/browser-use/video-use): transcription and editing helpers, installed as a Claude Code
  skill. Never edit it; call it.
- **Remotion**: see its licence for company use.
- **HyperFrames**: run with `npx hyperframes`.
