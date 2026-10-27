# Shorts: formats, output and the approval loop

How `shorts-editor` decides what to build and what to hand back. Two independent choices every time:
**which visual format**, and **which output**.

The fundamentals never change with either choice: captions, caption position, typography, safe areas, zoom cadence,
SFX taste, story shape and the QC checklist are the same on every short. They live in
`guides/short-form-editing-standard.md`, and that file wins over anything here.

## 1. Output: preview first, master on approval (DEFAULT)

**The default output is a LOW-RESOLUTION preview for approval. Never jump straight to the full-resolution master.**

| Stage | What | Why |
|---|---|---|
| 1. Preview | 1080x1920 (or 720x1280) H.264, small file, fast render, named `<slug>-preview-vN.mp4` | The creator watches and approves or sends notes. A 4K render of a rejected cut is wasted time. |
| 2. Approval | A yes, or notes. Notes mean a new preview, not a master. | |
| 3. Master | Only after an explicit yes: the full vertical master at the house resolution and fps (`config/brand.json` `output`), `<slug>-final.mp4`, with the full QC checklist. | |

The preview is a watchable proxy, not a different edit: same cut, captions, graphics and timing. Only the resolution
and bitrate change. Never simplify the edit to make a preview faster.

Stop after the preview. Stop again after the master. Never upload or schedule; that is a separate step.

## 2. Output: Final Cut Pro project (on request)

- Only when asked. If a high-production brief is ambiguous, ASK ("render or FCP project?").
- The house style does not get plainer in Final Cut.

## 3. Formats (the visual layer, the only thing that varies)

| Format | When | Spec |
|---|---|---|
| **Clean** (default) | One person to camera. Punchy cut, hook pill, captions, nothing else competing. | `CLEAN-STYLE.md` |
| **Dynamic / multi-mode** | Talking head plus chips, blur takeovers, receipt cards: something purposeful every 2-3 s. | `dynamic-shorts-format.md` |
| **Split screen** | A real asset belongs in one half: a screen recording, a demo, a clip. | `dynamic-shorts-format.md` M3 |
| **Podcast split screen** | Two speakers from a podcast episode. | `../podcasts/PODCAST-SHORTS-ENGAGEMENT-FORMAT.md`, via `podcast-shorts` |

A format is a visual treatment, never a licence to change the fundamentals. If a format seems to require breaking a
rule, stop and ask.
