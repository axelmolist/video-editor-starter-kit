# Voice and on-screen text rules

Copied to `brand/voice.md` by /setup. Every agent reads it before putting words on screen.

## Names Scribe mishears (always correct on screen)

| Heard as | Correct |
|---|---|
| (example) Acme Labs | AcmeLabs |

## On-screen text

- Spelling locale: set in `config/brand.json` `locale`.
- Case: sentence case for titles and hooks; proper nouns and acronyms keep their caps.
- Dashes: (e.g. no em dashes on screen; single hyphens only)
- Never shown on screen: (e.g. revenue figures, client names)

## Cutting preferences

- Long-form silence between sentences: (e.g. tight, max ~0.1 s)
- Music in long-form: (yes / no / hook only)
- SFX on overlays: (yes / no)
- Face pill on long-form overlays: (yes / no)
- Subtitles on solo long-form: (usually no)

## Shows

| Show | Intro jingle file | Logo for thumbnails | Hosts | Description closing line |
|---|---|---|---|---|
| (example) The Show | video/working-material/show-intro.mov | brand/logos/show-light.png | Host Name | New episodes every two weeks. |
