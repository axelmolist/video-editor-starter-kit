# Long-form YouTube edit format

The repeatable recipe for **solo long-form talking-head videos** (e.g. ~10-15 minute essays). Distinct from the
shorts formats (which never re-cut a finished edit's pacing this way) and from podcasts.

The creator hands over a **raw take file** (one continuous recording with silences, filler words, mistakes and
re-takes). The editor cuts it to a punchy final, inserts section title cards, adds a website lower third if the URL is
spoken, reframes and grades. Engine: the video-use skill for transcription (ElevenLabs Scribe, `ELEVENLABS_API_KEY`);
everything else is ffmpeg.

**Two BLOCKING text rules:**
- **Spelling in the configured locale.** Scribe writes American English. Normalise every transcript before it feeds
  subtitles, section cards or receipts (`video/lib/spelling.py`), and gate subtitle files with
  `python3 video/lib/spelling.py <subs> --check`.
- **No caption echo.** A section card, receipt headline, quote card or animation label never shows the same words as
  the subtitles at the same time. Default: rewrite or remove the graphic's text. Exception: when the text IS the beat,
  suppress the subtitles for that window. List every on-screen string with its window in `anim_texts.json` and gate it:
  `python3 video/lib/caption_dedupe.py <subs.srt|.ass> anim_texts.json` (exit 1 = blocked).

## 1. The cut

- **Silences:** cut out. Default ~0.15 s after the last word of a sentence and ~0.05 s before the first word of the next.
  Many creators want it tighter (max ~0.1 s between voice, cutting reading-pauses where they glance at the script):
  ask once and record the answer in `brand/voice.md`.
- **Filler words:** keep them when they read naturally; remove them only when it improves the flow. Natural, not robotic.
- **Re-takes:** **always take the LAST delivery of a repeated line.** Exception: if the latest attempt is itself broken
  (abandoned mid-sentence), fall back to the last *complete* take.
- **Pacing:** punchy, but not as punchy as a short.

### Mechanics that matter
- Transcribe word-level with Scribe, then map every phrase against the script to pick the final take of each beat.
  **Scribe gives you take SELECTION, not cut points.**
- **Cut points come from AUDIO.** Scribe inflates a word's `end` to hide the following pause and sometimes anchors a
  `start` seconds early. Build a silence map with `silencedetect=noise=-35dB:d=0.08` (adjust to the speaker: aim ~10 dB
  below their mean speech level) and **snap every cut INTO a detected silence**, so you never clip a word.
- **Gap-less grafts:** when two good fragments butt together with no silence (a self-correction), cut at the word
  boundary and let the fade mask it. Flag these for an ear-check. Watch for doubled words.

## 2. Section title cards

- A card at **every section boundary**, including one after the hook and one before the outro, not just act breaks.
- Ask whether the creator makes the cards themselves (e.g. exported from Final Cut) or wants them built. If supplied as
  clips: insert each at its boundary with silent stereo PCM so it slots into the click-free concat. **Gotcha:** Final
  Cut exports can carry two video streams; map only `0:v:0`, or `-shortest` clamps the card to one frame.
- If you build them: use the `TitleCard` Remotion example as the starting point, in the brand's palette and fonts.

## 3. Website lower third

When the creator says their website, show it as a lower third under the face: text colour, no box, over a dark part of
the background, body font bold ~44 px at 1080, gentle fade, on screen for the URL delivery (~3 s).

## 4. Reframe

From a locked 4K wide shot: head centred horizontally, eyes on the upper-third line. A modest punch-in (~15%) also
removes loose foreground (desk, mic). Re-measure per recording with a thirds-grid frame; keep the hands in frame.

## 5. Colour grade

Apply the house long-form grade (`video/instructions/style-config.json` `grade`, built with the `colour-grader` agent)
to every long-form video. Record it as an ffmpeg filter plus a note of the intent. ffmpeg's `colortemperature` runs
inverted against Final Cut's temperature. Re-tune magnitudes per shooting location; keep the look.

## 5b. Click-free audio (critical)

Independently encoded **AAC** segments joined with the concat demuxer get an encoder-priming gap at every boundary:
**audible clicks**. Fades on top do not fully fix it.
- Give each segment **lossless PCM** audio (`-c:a pcm_s16le`) in an `.mkv`, concat losslessly, and encode AAC **once**
  at the very end (`-c:v copy`, loudnorm, `-c:a aac`).
- Put a **30 ms `afade` in and out on every segment**, so every join is zero-to-zero.
- Because cuts sit in silence, the fades never audibly touch speech.

## 6. Output

- **Resolution rule:** footage in at the house resolution goes out at the same resolution and fps
  (`config/brand.json` `output`). The reframe crops a window and scales back to full size.
- Per-segment extract (crop + grade baked in) -> lossless concat with the card clips -> final pass with the lower third
  and two-pass loudnorm (-14 LUFS / -1 dBTP). No burned subtitles unless asked.
- Layout: `video/projects/youtube-long/<slug>/final-footage/<slug>-final.mp4`; working data in `editor-files/`.
- Self-check every cut boundary (discontinuities, pops, clipped speech, lower-third placement) before showing anyone.
