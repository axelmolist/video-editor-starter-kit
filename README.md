<!-- DRAFT: to be audited by the copywriter before publishing. -->
# Video editor starter kit

A working setup for editing video with an AI coding agent such as
[Claude Code](https://claude.com/claude-code) or Codex: YouTube long-form, podcast episodes, podcast shorts, solo
shorts, vlogs, animated graphics, colour grading and captions.

It is a repository the agent works from: the agents, the editing rules they follow, and the code they run (ffmpeg
pipelines in Python, motion graphics in Remotion, stills in HTML/CSS). Your brand, fonts, palette and keys are asked
for the first time you open it in Claude Code, and stored locally.

## Quick start

```sh
git clone https://github.com/axelmolist/video-editor-starter-kit my-video-studio
cd my-video-studio
claude
```

Then say anything ("hi" is fine). The agent sees the kit is not set up yet and walks you through onboarding. Full
steps and requirements: **[SETUP.md](SETUP.md)**.

## What it does

| Agent | Give it | You get |
|---|---|---|
| `youtube-long-editor` | One raw take | A story-first cut with section cards, receipts, animations and chapters, or a Final Cut project |
| `podcast-editor` | Multicam files + one mic per person | The switched episode, a captioned cold-open hook, a thumbnail and the description |
| `podcast-shorts` | A podcast episode | Vertical shorts: animation on top, speaker below, reaction cutaways, fixed captions |
| `shorts-editor` | A raw talking-head clip | A clean or dynamic vertical short, preview first |
| `youtube-vlog` | A pile of rushes | A spine-first edit as a Final Cut project |
| `colour-grader` | A clip | Brightness, then colour, picked from rendered options with scopes |
| `video-editor` | Anything | Routes the job; adds captions and graphics to a finished cut |

## The ideas

**Your taste lives in config, not in code.** Palette, fonts, logos, caption style, spelling and output format sit in
`config/brand.json` and `video/instructions/style-config.json`. Change them and every agent follows.

**Cut on the audio, not the transcript.** Transcripts say what was said. The waveform says where to cut.

**Preview before master.** Agents show a low-resolution preview or a review page and wait for your go-ahead before
rendering finals. Nothing is uploaded or scheduled for you.

## Requirements

macOS or Linux, ffmpeg (with libass), Node.js 22, Python 3.9+, and a paid ElevenLabs account for transcription.
Optional: Higgsfield for generated images and video, S3-compatible storage and Buffer for scheduling, Final Cut Pro for
the project-file workflows.

## What is not here

Your footage, your projects and your keys. `video/projects/`, media files, `.env` and `config/brand.json` are
gitignored.

## Licence

MIT. See [LICENSE](LICENSE). Third-party tools keep their own licences: video-use (MIT), Remotion (company licence
above a size threshold), HyperFrames.
