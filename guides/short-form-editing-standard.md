# Short-form editing standard

The fundamentals every vertical short shares, whatever its format (`video/instructions/formats/shorts/`). The golden
rule: **the edit exists to make a sound-off viewer feel the message and a sound-on viewer feel the beats. Emphasise
what matters, drop what doesn't, and never let the craft call attention to itself.**

Brand values come from `config/brand.json`; this file never names a colour or font.

## 1. Talking-head layout

1. **Framing:** the speaker's chin sits on or just above the frame's horizontal centre line. Measure per clip on real
   stills; never guess. Scale punch-ins around the chin point. If the source has too little headroom, punch in slightly
   or fill the top with a blurred extension of the background. Always follow a vertical stretch with `setsar=1`.
2. **Hook/title above the head, on screen for the whole short**, title font, never touching the hair.
3. **Captions just under the chin** (or fixed on the centre line for split-screen formats), caption font, text colour,
   soft drop shadow, no outline, upright, never ALL CAPS, proper names capitalised.
4. **QC (hard fail):** stills at start, middle and end of every piece, including punch-ins: chin on the line (~30 px),
   hook clear of hair, captions in place, ffprobe SAR 1:1.

## 2. Phone fill-crop safe zone (BLOCKING)

TikTok and Reels fill a 19.5:9 phone by scaling a 9:16 file to full height, cutting **~9% off each side**.
All overlay content inside **x 14%-86%**; nothing important above **12%**; keep the right rail (from ~46% height down)
and the bottom ~20% clear of platform UI. Big takeover words **auto-fit** inside that width. QC: crop a frame to
921:2000 centred and check nothing touches the edges.

## 3. The title pill

It tells a scroller exactly what the short is about and its payoff. Write it like packaging: clear, specific, the
real claim or the real number; not a clever or cryptic line. Sentence case (proper nouns and acronyms keep caps). One
accent word at most.

## 4. Captions: curated emphasis (Dynamic style)

- **Distil, don't transcribe.** Drop filler (and, the, so, just, you know); the kept words still read as a sensible line.
- **Dramatic size swing:** base words small, the words that matter ~2-2.5x bigger, one big unit per cue.
- **Never drop a word whose loss changes meaning** (a "not", a qualifier, a number).
- **Emphasise the meaningful unit**, not a stray word: "code coverage", not "coverage". Read the emphasis back alone:
  if it does not carry the point, you picked the wrong span.
- **Markup must handle multi-word spans.** Parse emphasis tokens with a regex, never a per-word split, or brackets leak
  on screen. QC: grep the final `.ass` text for literal markup; must be zero.
- **All text upright and horizontal.** No synthetic shear or skew. Real italics only if the brand has a licensed italic.
- Spelling in the configured locale (`video/lib/spelling.py`) and a per-channel spelling patch for names Scribe
  mishears (kept in `brand/voice.md`).
- **No caption echo:** a graphic never shows the same words as the captions at the same time
  (`video/lib/caption_dedupe.py`).

## 5. Zooms: few, big, purposeful, calm

- **A zoom change roughly every 4-5 s.** Never static for more than ~5 s; never a twitch under ~3 s.
- **2-second dwell:** every zoom state holds still for at least 2 s after its move completes. This kills the seasick feel.
- Hard emphasis word -> instant cut-in (~1.5-2x, room permitting); an ordinary sentence -> a gentle push (~1.3-1.5x) then
  a pull-out; a reveal -> zoom out as a panel lands. Never clip the head at the tightest point.

## 6. Full-screen blur takeovers

For the 1-2 biggest moments. A light gaussian blur only (e.g. `gblur=sigma=12` at 4K); do not darken or tint (it looks
dirty). One big upright word in the text colour with a drop shadow; a payoff word may be the accent. Captions
suppressed for the window. One takeover per ~15-20 s. The audio never pauses.

## 7. Sound effects

Purposeful and under the voice: ~1 hit per 4-8 s, trimmed to the transient, ~-13 to -16 dB below dialogue, never on a
word. A soft click when a graphic lands; a swipe when a panel slides in; a click on EVERY row of a list as it appears;
a deep hit for a gravity beat. Never a sound on every beat. Library: `config/brand.json` `paths.sfx`.

## 8. Receipts

A real screenshot in a card, landing on the spoken line it proves, with a small eyebrow and a muted source line. Every
spoken money figure or factual claim gets its on-screen source. Keep a manifest mapping each receipt to its short.

## 9. Story shape and the end

- Hook by ~second 3, then the substance, then the CTA.
- **Let the point finish (BLOCKING):** never end a clip or a spliced segment mid-sentence or mid-thought. Cut earlier
  only if, after the sentence ends, the speaker switches topic or rambles.
- **No doubled words at splice joins** ("so, so", "the the"). Read every join aloud.
- When the speaker misspeaks a fact, never change their audio: show the correct value in the graphic, optionally with
  a small accent "*correction" over the caption.

## 10. QC checklist (read the FINAL, every time)

1. ffprobe: house resolution and fps, no rotation, audio duration == video duration, size under the cap.
2. Title: clear, sentence case, in the headroom.
3. Captions: curated, upright, clear of face and panels, emphasis correct, locale spelling clean, dedupe clean.
4. Zooms: a change every ~4-5 s, every state >= 2 s, head never clipped.
5. Takeovers: light blur only, word legible and inside the safe zone.
6. Safe zone: every element inside x 14%-86%, nothing above 12%.
7. SFX synced, under the voice, nothing buried.
8. Receipts legible, on the right line, sourced.
9. The point lands; no doubled words at joins; no clicks at joins.

## 11. Re-render gotchas

- On any change to the cut, **force-rebuild the audio mix**; a stale mix leaves old audio under new video. Verify audio
  and video stream durations match.
- Never run two builds writing the same output path at once; concurrent writes corrupt the mp4.
- Zoompan expressions can silently under-render: verify the magnitudes on real frames.
- Batch builds: 2-3 concurrent 4K renders at most, each with its own output path; verify every returned file yourself.
