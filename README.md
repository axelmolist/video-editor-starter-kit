# Video editor starter kit

Ten video agents for [Claude Code](https://claude.com/claude-code) or Codex, and the code they run. Give them raw
footage and they cut YouTube long-form, podcast episodes, podcast shorts, solo shorts and vlogs, then grade, caption
and animate them.

The repository holds three things: the agents, the editing rules they follow, and the code they call (ffmpeg
pipelines in Python, motion graphics in Remotion, stills in HTML/CSS). The first time you open it in Claude Code, it
asks for your brand, fonts, palette and keys, and keeps them on your machine.

## Quick start

```sh
git clone https://github.com/axelmolist/video-editor-starter-kit my-video-studio
cd my-video-studio
claude
```

Then say anything ("hi" is fine). The agent sees the kit isn't set up yet and walks you through onboarding. Full
steps and requirements are in **[SETUP.md](SETUP.md)**.

## What it does

| Agent | Give it | You get |
|---|---|---|
| `youtube-long-editor` | One raw take | A story-first cut with section cards, on-screen sources for the facts, animations and chapters, or a Final Cut project |
| `podcast-editor` | Multicam files + one mic per person | The switched episode, a captioned cold-open hook, a thumbnail and the description |
| `podcast-shorts` | A podcast episode | Vertical shorts: animation on top, speaker below, reaction cutaways, fixed captions |
| `shorts-editor` | A raw talking-head clip | A clean or dynamic vertical short, preview first |
| `youtube-vlog` | A pile of rushes | A spine-first edit as a Final Cut project |
| `colour-grader` | A clip | Brightness, then colour, picked from rendered options with scopes |
| `video-editor` | Anything | Routes the job; adds captions and graphics to a finished cut |

The other three (`animation-locator`, `diagram-designer`, `animation-generator`) are the animation pipeline the
editors call.

## How it works

**Your look lives in config, not in code.** Palette, fonts, logos, caption style, spelling and output format sit in
`config/brand.json` and `video/instructions/style-config.json`. Change them and every agent follows.

**Cuts come from the audio.** ElevenLabs Scribe marks words as ending later than they really do, so the agents find
cut points in the waveform and keep quiet starts and trailing consonants intact.

**You see it before it's final.** With `export_approval` on (the default), agents show a low-resolution preview or a
review page and wait for your go-ahead before rendering a final file. Nothing is uploaded or scheduled without your
say-so.

**AI-generated b-roll is off by default.** It often reads as filler, so the agents reach for your footage and
animation first. You can turn it on in `config/brand.json`.

## Requirements

macOS or Linux, ffmpeg (with libass), Node.js 22, Python 3.9+, and a paid ElevenLabs account for transcription.
Optional: Higgsfield for generated images and video, S3-compatible storage and Buffer for scheduling, Final Cut Pro for
the project-file workflows.

## What isn't here

Your footage, your projects and your keys. `video/projects/`, media files, `.env` and `config/brand.json` are
gitignored.

## Licence

MIT. See [LICENSE](LICENSE). Third-party tools keep their own licences: video-use (MIT), Remotion (a company licence
above a size threshold), HyperFrames.
