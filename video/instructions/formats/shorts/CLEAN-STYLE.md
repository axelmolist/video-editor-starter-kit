# CLEAN style: talking-head shorts (the default)

A simple, punchy production: the cut flows, there is a hook and there are captions, and nothing else competes with the
speaker. Clean is the default for every raw talking-head short. The Dynamic format (`dynamic-shorts-format.md`) is used
when the creator asks for it.

**Builder:** `video/lib/clean_short.py <config.json>` for the preview, then `--4k` for the master. One config per
short; the same code renders both. The config format is documented at the top of `clean_short.py`.

## Phone fill-crop safe zone (BLOCKING, every vertical short)

TikTok and Reels fill a 19.5:9 phone screen by scaling to full height, which cuts **~9% off EACH side** of a 9:16 file.
- **Sides:** all overlay content (pills, titles, captions, animations) inside **x 14%-86%** of the frame.
- **Top:** nothing important above **12%** (platform search bar and header).
- **Right rail:** from ~46% height down keep the right side clear of the action icons; keep the bottom ~20% clear.
- **QC gate:** crop a frame to 921:2000 centred and check nothing touches the edges or the platform UI.

## The look (numbers at 720x1280; the master is x3)

| Element | Rule (defaults; tune in the config) |
|---|---|
| **Cuts** | No silence between sentences. Keep **0.02 s before** each sentence's first sound and **0.03 s after** its last. Find both boundaries from the waveform (Scribe times are only the starting point) and never eat audible sound. Never cut inside a sentence: natural pauses come between sentences. |
| **Takes** | Drop false starts and retakes. Keep the last complete clean take of each line, in script order. Check audio levels in long gaps for speech Scribe missed. |
| **Framing** | Chin anchored on the centre line, chest-up (`base_zoom`, e.g. ~1.65x of the upright frame; wider camera set-ups need more). Check that the hook clears the hair on punched frames. |
| **Motion** | A very slow continuous creep (~+0.11x over the short). **Punch-ins x1.25** (hard cut, held to the end of that segment) on the relevant line, roughly every 4-5 s. |
| **No full-screen text** | No blur takeovers, chips, emphasis captions or SFX by default. |
| **Guest clips** | Full screen, never split screen (unless you have real listening footage). A 9:16 crop of the 16:9 source, panning to follow the speaker. Grain only, no grade, no hook. Use the speaker's single strongest line. |
| **Hook** | A pill in the palette's text colour with dark text in the title font, centred, on screen the whole short except over guest clips. Wording: a **plain topic label** a cold viewer understands. Position just above the head at the tightest punch-in, never touching the hair. |
| **Captions** | Caption font, ~43 px, white, soft drop shadow (no outline), centred just under the chin. One line of at most ~18 characters, balanced so no orphan words, numbers as digits, no full stop or comma at the end of a line. Spelling in the configured locale. |
| **Grade** (host only) | The house grade in `clean_short.py` (`GRADE_LUT` + `TINT`) or the one the colour-grader agent built with you. |
| **Grain** | Light mono film grain (std 0.014), drawn at 720x1280 and scaled, so the master's grain looks the same. |
| **Audio** | -14 LUFS, true peak -1.5. A backing track, when supplied, starts on its first beat at 0 s and ends with the short. |

## Pipeline

1. **Probe.** Rotation (phone and camera clips are often sideways with no rotation tag: set `transpose`). Log footage
   (S-Log, D-Log): convert to Rec.709 with the manufacturer's LUT first. A separate audio file: sync it and mute the
   camera audio. Measure the chin anchor on upright stills.
2. **Transcribe** with Scribe (the video-use skill's `helpers/transcribe.py`), plus any guest clip region.
3. **Write `editor-files/clean.json`**: slug, version, timeline (kept sentences and guest clips), punch-ins, hook, anchor.
4. **Render the preview** at 720x1280, versioned `-vN`. Never overwrite a render: bump `version`. The builder refuses
   to overwrite and snapshots the config into `build-vN/`.
5. **QC before presenting:** ffprobe (720x1280, house fps); a contact sheet; a join audit (every cut lands in silence);
   the hook clears the head at the tightest punch-in; captions read cleanly over guest clips.
6. **On approval only**, run `--4k` for the 2160x3840 master. Check stills against the approved preview.
