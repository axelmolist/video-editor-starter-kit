# Brand video guardrails (the taste layer)

Machine-readable settings live in `video/instructions/style-config.json` and `config/brand.json` (numbers win there);
this file owns taste and principle. Every agent reads it before adding anything to a video. Brand voice and naming
live in `brand/voice.md`.

## Iron rules (hard fails)

1. **Never cut a finished source.** When the creator hands over a FINAL edit, only captions and animation are added.
   No trimming, speed changes or reordering; output duration equals the source exactly. (Raw-footage formats such as
   long-form, vlog and clean shorts DO cut, under their own specs.)
2. **Minimalism in the graphic, not in the count of beats.** Many beats can carry a graphic, but each is ONE simple
   primitive: the least graphic that conveys the idea. Energy comes from scale and motion, never from adding elements.
3. **Allowed primitives:** `counter`, `line_graph`, `pie`, `bars`, `arrow`, `text_slam` (see `video/lib/primitives.py`
   and the Remotion kit). If a beat does not reduce to one clean primitive, it stays captions-only.
4. **Crisp text only.** Full opacity once revealed, high contrast. Never run a line, arrow, divider or bar through text.
   Place labels OUTSIDE the graphic area so lines and bars cannot reach them.
5. **On-screen text follows `brand/voice.md`**: spelling locale, case, punctuation (many brands ban em dashes on
   screen), names spelled correctly.
6. **No claim a graphic implies that the speaker did not make.** No invented numbers, sources or logos. If the brand
   has topics it never shows on screen (revenue, client names), they are listed in `brand/voice.md`.
7. **Size cap for scheduled shorts:** keep finished shorts under your scheduler's ceiling (many fail above ~200 MB).
   Run `video/lib/fit_under_size.py` last (a no-op if already under); lower only the bitrate, never the resolution.
8. **Motion discipline.** A graphic is moving while on screen, or it completes its motion and holds still until it
   leaves. Never start-stop-start. The climax lands the key word; the graphic clears ~0.5-0.8 s after.
9. **Taste, not gimmicks.** No checkmarks, clip-art icons, emoji or gimmick symbols. Convey meaning through the graphic
   itself (a bar reaching a line = it works; an accent-coloured shortfall = it fails).
10. **No intricate alignment.** If a design needs many small elements aligned (labels under bars, grids, calendars) and
    there is any risk of misalignment, simplify radically or skip. A misaligned graphic is worse than none.
11. **One beat = one sentence or idea.** Never merge two ideas into one graphic.
12. **Full-screen text slams are valid:** background colour + one phrase, timed to the word. Zero alignment risk.
13. **Generated media** (AI b-roll or stills) only if `config/brand.json` `generated_media` allows it.

## Aesthetic

Palette roles from `config/brand.json`:

| Role | Use |
|---|---|
| `background` | base and full-screen takeover background |
| `primary` | secondary surfaces, gradients, cards |
| `text` | text, lines, marks |
| `accent` | the SINGLE accent: the one element that is the point. Never large fills. |
| `muted` | secondary labels, axes |

**Type:** titles use the title font in the accent or text colour; labels, axes and captions use the body and caption
fonts. Register the real weights. **Font loading in HTML/CSS (critical):** HyperFrames does NOT load `url(file://...)`
fonts; it silently falls back to a serif. Use `@font-face { src: local("<exact face name>") }` or an embedded base64
`data:` URI (`design-studio/fonts-embedded.css`). Verify the weight actually rendered: a weight swap must visibly change
the output. Never trust a lint that only checks an `@font-face` exists.

The `design_language` field in `config/brand.json` is the creator's own description of the look. Read it before
designing anything and match it.

## Captions

`video/lib/captions.py` with the `captions` block of `style-config.json`: words per cue, position, case, outline mode
(always / adaptive / never), accent words. Captions sit clear of the face and the platform UI.

## Animation presence

- Full-screen takeovers are fine (the voice continues under them): cutting to a graphic is not covering the face.
- When the speaker IS on screen, never cover their face with a card.
- Hold each graphic long enough to read at 1x. Sync the landing frame to the word it illustrates.

## Style references (the compounding asset)

After a good video, save its recipe in `video/working-material/style-references/<slug>/`: the designer specs (JSON),
caption settings and 2-3 screenshots. By the third video of a type, the pattern is near one-click.
