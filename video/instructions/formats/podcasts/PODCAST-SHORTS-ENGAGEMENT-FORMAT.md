# Podcast shorts: the ENGAGEMENT format

**The single source of truth for every vertical short cut from a podcast episode** (host or guest clips, remote or in
person). Owner: the `podcast-shorts` agent. Other files point here; they do not copy it.

Code: `video/lib/podcast_shorts_engaged/` (see section 14). Worked config: `video/lib/podcast_shorts_engaged/episodes/example.json`.
Brand values (palette roles, fonts, fps, locale) come from `config/brand.json`; numbers below are proven defaults that
you may tune per show, but change them in the episode config or this file, never ad hoc in one short.

---

## Phone fill-crop safe zone (BLOCKING, every vertical short)

A correct 9:16 file is still CROPPED on the phone: TikTok and Reels fill a 19.5:9 screen by scaling to full height,
which cuts **~9% off EACH side**. Desktop players letterbox, so you will not see it in a preview.

- **Sides:** all overlay content (cards, pills, titles, takeover words, animations, captions) inside **x 14%-86%**
  of the frame (x 302-1858 at 2160 wide). 10% is not enough.
- **Top:** nothing important above **12%** (y 461 at 3840): platform search bars and headers sit there.
- **Right rail:** from ~46% height down, keep the right side clear of the like/comment/share icons; keep the bottom
  ~20% for the platform caption and username.
- **QC gate before any render:** crop a frame to 921:2000 centred (the phone screen ratio) and check nothing touches
  the edges or the platform UI.

## 1. What gets made

Per short, two files from one pipeline:

| Version | What it is |
|---|---|
| **Engagement** (`<slug>-engagement.mp4`) | Split screen with an ANIMATION on top and the person on camera below, full frame for the hook, reactions, punch lines and punch-ins. Something changes about every 0.5-1.5 s (never more than 2 s). **The headline format.** |
| **Clean** (`<slug>.mp4`) | The same cut, full frame throughout: speaker plus the listener's reaction cutaways, the same captions and hook. A companion; ask whether the creator wants it. |

## 2. Clip selection and cutting

1. **The moment.** A value moment from the short's OWNER (host or guest): a lived story or an original thesis. Never
   isolate a guest's qualified or provocative line without its context. Speaker attribution comes from the isolated
   per-mic transcripts, never from mixed-audio diarisation.
2. **Length: 30-40 s** by default. The other person's reply counts inside the cap. If a reply cannot finish in time,
   ask; do not stretch on your own.
3. **Hook first.** Open on the line that states the thesis. The on-screen hook card names what the viewer gets.
4. **Never end mid-sentence.** No doubled words at splice joins.
5. **Minimal cuts, all in silence.** Cut only repeats, false starts, a drifting middle or dead air. Every cut sits in a
   quiet gap outside the complete sound: never eat into quiet onsets or trailing consonants. Keep the tail of A, start
   B ~0.1 s before its first sound; total join silence ~0.12-0.2 s. Never drop a qualifier that changes meaning.
6. **End on the other person's reply** where one exists ("yes", "completely agree", their first sentence), ending on
   a complete phrase.
7. Segments are authored in HOST-AUDIO time (the per-mic transcripts' clock) and snapped to the host camera's frame
   grid (picture = audio + the camera's A/V offset).

## 3. The listener: reaction cutaways

- **Full-screen cutaways to the listener** from their own camera at the SAME moment. Genuine reactions only; never
  borrow a reaction from another moment.
- **~1.0-1.2 s** when they are just listening; **~2 s** on a smile or big reaction.
- **Every ~4-6 s**, varied. None in the hook (first ~3 s) and none on the speaker's key or payoff words.
- **Cover every jump cut** with a cutaway.
- **Never on silent lips.** If the listener visibly talks while their mic is gated closed, open the mic for that word
  or cut away somewhere else.

## 4. The engagement layout

```
 2160 x 3840 (vertical)
 +------------------------------+  y 0
 |  [ HOOK CARD, whole short ]  |  top edge on the safe line; title font; 1-2 lines
 |   TOP PANEL 2160x1920        |  split states: the animation (or a literal real clip)
 |   animation, never static    |  content >= 30 px under the card
 |   ......(band kept empty)....|  bottom ~110 px of the panel = background only (caption band)
 +==== seam, 6 px, y 1917 ======+  y 1920 = captions, FIXED, in every state
 |   BOTTOM PANEL 2160x1920     |  the speaker, or the listener's reaction
 +------------------------------+  y 3840
 Full-frame states: same hook, same caption row; the picture reaches every edge.
```

**States** (authored per short as `(out_t, kind, spec)`):

| Kind | What | When |
|---|---|---|
| `F` full frame | The speaker, or the listener's cutaway | The opening hook line, every cutaway, punch lines, the reply ending |
| `F` + punch-in | ~1.08 about the mouth row, reduced to keep the hair clear of the hook | One or two per short on the strongest words |
| `S` split | Top: the animation track. Bottom: the camera panel | ~60-68% of the runtime; one animation scene per idea, 0.8-5 s each |
| `X` full real clip | A literal real clip, full frame | Rare; only under the B-roll rule |

**Change cadence (BLOCKING).** Something visibly changes about every 0.5-1.5 s and never more than 2.0 s: state
changes, shot changes and the animation's own steps. A punch-in the hook rule had to drop is NOT a change.

**Captions and the hook are identical across states**: the caption row never moves, the hook never moves, and a cue
that spans a state change continues without re-popping.

## 5. Animations (top panel) and B-roll

- **Each beat strengthens the exact words** and lands on the spoken word, frame-accurate. Only facts that were said:
  no invented numbers, names or claims.
- **No reused designs**, inside a short or across a batch. If a moment does not earn a fresh visual, stay full frame.
- **Never static for more than 0.5 s.** Every scene keeps moving (a slow push, a drifting background, sequenced reveals).
- **Style:** the palette roles from `config/brand.json`. Panels use `background` (an almost flat, slightly darkened
  radial reads better than a strong gradient); `accent` is the single sparing highlight. Condensed or display weights
  of the title font for headlines and numbers; the body font for small labels.
- **Layout hygiene (BLOCKING):** no text or chip sits on a graphic unless deliberate; mixed-colour words on one line
  share a baseline (measure the real ink, not the canvas); a centred phrase re-centres after a word swap; the caption
  band at the seam stays empty; content stays 30 px under the hook card.
- **Comp spec:** one Remotion composition per short, 1080x960, spanning the WHOLE short, rendered `--scale=2` to
  `editor-files/alt/top_anim.mp4`; the compositor shows it only inside split states. Load fonts through the font gate
  so nothing is captured in a fallback face.
- **No caption echo:** the animation never shows the same words as the captions at the same time. Default: rewrite or
  remove the animation's text. Exception: when the text IS the beat (quote card, typography beat), add a `suppress`
  window. Declare every on-screen string in the short's config as `anim_texts: [{id, start, end, text}]`;
  `cli.py plan` runs `video/lib/caption_dedupe.py` and `cli.py render` refuses on any overlap.

**B-roll ladder:** the creator's own footage > specific real archive of the exact named thing > animation > (never)
generic stock. B-roll only when it is literal (the actual person, place or event named), real, at least 1080p and
matching the look. Generic stock reads as cheap. AI-generated video only if `generated_media.allow_ai_broll` is true in
`config/brand.json`. List every clip with its source in `editor-files/alt/broll_sources.md`. A literal clip gets a
slow ~7% pan so it is never static.

## 6. The hook card

- On screen for the whole short, at the top: a card in the palette's `text` colour, `background`-coloured text, ONE
  `accent` key phrase (`{phrase}` markup), sentence case, soft shadow, title font.
- **Size:** `HOOK_SCALE` (1.30 by default) x a 38 px base on the 1080 grid; padding 31/16, radius 21. Top edge on the
  safe line, inside the safe width. If it does not fit one line it wraps to **two balanced lines**: at least 2 words per
  line, never a split accent phrase, never shrunk.
- **Never touches the hair**: at least 40 px between card and hair in every full-frame state, at least 20 px inside
  punch-ins. Move the punch-in pivot up before reducing the zoom; never let a punch-in drop to 1.0.
- **It explains the video to a cold viewer, almost like a YouTube title.** Clear about what the short is, still
  specific to the speaker. Clever lines that need the video to decode them fail. Never a money figure.
- Spelling in the configured locale (`cli.py plan` reports off-locale spellings; must be empty).
- PIL builds without HarfBuzz draw unkerned glyphs. If the card looks "collaged", set `"hook": {"renderer": "chrome"}`.

## 7. Captions

- **Fixed on the frame's horizontal centre line (y 1920 of 3840) in EVERY state.** They never move.
- Caption font, `text` colour, soft drop shadow (blurred ~72% opaque near-black copy behind sharp text, offset
  +2.5/+5 on the 1080 PlayRes; no outline), `accent` emphasis on the meaningful unit (`{phrase}` markup). Sizes 70 /
  78 emphasis / 64 for the other person on the 1080x1920 PlayRes. The OTHER person's lines (`~` prefix) are in `muted`
  and slightly smaller. Cues run from the first spoken word (-50 ms) to the last (+450 ms, never into the next cue);
  a quick 88% -> 100% pop.
- Spelling normalised by `spelling.py` (Scribe writes American English). Author cues from `cli.py words` output.
- Never italic, never ALL CAPS, proper names capitalised, no markup leaks (the build fails on a leaked brace).
- Suppressed only where the animation itself carries the words.
- **Framing:** prefer the chin at or just above the centre line so captions sit under it. When that cannot coexist with
  a covered bottom edge and the hook clearance, captions stay on the centre line over the mouth: **that fallback is
  accepted; moving the captions is not.**
- **Never uncover an edge**: the picture reaches every edge with real camera. A blurred, mirrored wall plate is allowed
  ABOVE the source only; never a flat band at the bottom.

## 8. Grade and audio

- **Grade = the episode's grade**, so the shorts match the long-form. Record it in the episode config. Never re-grade
  footage that arrives already graded. ffmpeg `colortemperature` runs inverted against Final Cut's temperature.
- **Audio:** host mic open; the other mic gated open only in their reply windows (30 ms ramps, per-window gain to level
  within ~1.5 LU); short edge fades; light bus compression and limiter; two-pass linear loudnorm to -14 LUFS / -1.5
  dBTP. No SFX and no music in this format by default. Measure the host file's A/V offset per episode.

## 9. Technical spec

- 2160x3840 at the house fps, CFR, H.264 high CRF 20 (maxrate 32M), yuv420p, AAC 192k 48 kHz, faststart, SAR 1:1,
  under your platform size cap.
- **Frame discipline (remote-recording files are often VFR; never relax):** trim each live branch on real time and
  renumber 1:1 at the house fps straight after the trim (`settb=1/FPS,setpts=N,trim=end_frame=n`); a webcam source gets
  `fps=FPS` on its own branch first; every vstack/overlay input has `settb`; joins use `shortest=1`; **never
  `setpts=N` after a multi-input filter**; anchor segment starts on the real nearest source frame (ffprobe).
- Folder: `video/projects/podcasts/<series>/<episode>/shorts/<slug>/` with `editor-files/` and `final-footage/`.

## 10. Build pipeline

1. **Read** this file and the episode folder (per-mic transcripts, audio, camera files, the long-form grade). Probe
   every camera file (fps, VFR, rotation) and measure the host A/V offset on a clap or a hard consonant.
2. **Pick the moments** (or take the creator's list). Per short: segments, the other mic's reply windows and gains, the
   shot list, the hook text, the caption cues. `cli.py <episode.json> words <slug>` prints the kept words in output time.
3. **Measure the cameras** on real stills (hair-above-mouth, chin-below-mouth, wall plate; for a webcam the face centre,
   hair row and mouth row) and run the face track for tracked cameras:
   `python3 video/lib/podcast_shorts_engaged/track_faces.py <episode.json> --model face_landmarker.task` (needs
   mediapipe). Store the numbers in the episode config.
4. **Plan the engagement states**: splits, which words each animation lands on, punch-ins, animation step times.
   Storyboard first; no two beats share a design.
5. **Dry plan, no video:** `cli.py <episode.json> plan <slug>` writes captions, hook card, layer and compositor graphs,
   the change log, and runs the pre-render gates. Fix until every gate passes.
6. **Audio:** `cli.py <episode.json> audio <slug>`. Listen to every join.
7. **Animations:** build the Remotion job (`remotion/src/jobs/<episode>-shorts/`), register it in
   `src/jobs/index.ts`, and render **stills** at each beat's peak frame for review.
8. **Review loop** (section 11) until the creator signs off the beats.
9. **Render only after the creator's explicit go-ahead:** `cli.py <episode.json> render layers|engagement|clean <slug> --approved-export`.
10. **Render gates** (section 12), then report and stop. Never upload, never schedule.

## 11. Review loop

- **Stage A, no approval needed:** a review page with, per short, the hook, the cut, the state plan, and per beat: the
  words it lands on, what it shows, and a still at its peak.
- **Stage B, with go-ahead for preview video:** a 1080x1920 preview composite cut into per-beat clips.
- **Stage C, explicit export approval:** the full engagement + clean renders.

## 12. Delivery gates (all hard fails)

Pre-render (`cli.py plan`): caption rows fixed; plan length equals the cut; change-log max gap <= 2.0 s; hair >= hook
bottom + 40 px in full frame and + 20 px in punch-ins; bottom edge covered with real picture; caption-dedupe clean;
hook spelling in locale.

Render (`cli.py verify <slug>`):
1. Frames = duration x fps (+-1), constant frame rate, audio duration = video duration.
2. No duplicate-frame runs (full-resolution framemd5).
3. Clean decode.
4. Sync: the source frame on each output frame is the expected picture time within 20 ms.
5. Edges covered: no flat band on the bottom edge of any frame.
6. Caption band in every split holds background only.
7. Caption baseline identical in every state; hook clear of hair on stills of every state.
8. Size under your platform cap.

## 13. Known pitfalls

| Pitfall | Fix |
|---|---|
| **VFR stutter** ("plays half a second then freezes"): `setpts=N` after a concat/vstack renumbered frames from both streams | Section 9 frame discipline; framemd5 dup-run gate on every render |
| **Empty bottom band** under the speaker | The picture must reach every edge; plate above only; per-segment scale from the lowest mouth row |
| **Captions moving between states** | One fixed row in every state; split cues at state boundaries without re-popping |
| **Hook touching hair** | Hook-aware framing, punch-in limiter, stills of every state |
| **A bigger hook kills punch-ins**, leaving 2+ s with no change | A dropped punch-in is not a change: add another change until max gap <= 2 s |
| **Mixed-colour baselines drift** | One flex row with a shared baseline; measure the ink |
| **Stock B-roll looks cheap** | Animation first; literal real footage only |
| **Silent lips** (listener talking with a gated mic) | Open their mic for it or cut away elsewhere |
| **Italic captions / phantom commas** in libass | Select the face by exact name with Bold=0; keep `Name` in the `[Events]` Format line |
| **FCPXML imports crash Final Cut** (VFR sources declared CFR, 0-duration stills, hand-made uids) | Render from the toolchain; for an FCP project, transcode cameras to CFR ProRes first and let FCP mint uids |
| **Stale audio under a new cut / concurrent writes corrupt an mp4** | Rebuild audio on every cut change; one writer per output path |

## 14. Toolchain

`video/lib/podcast_shorts_engaged/` (Python with numpy + Pillow; the video-use skill's venv works):

| Module | Role |
|---|---|
| `config.py` + `episodes/<episode>.json` | Per-episode config: cameras (measured geometry, A/V offset), audio, grade, punch-in, hook scale, and per short: segments, reply windows, shot list, cues, states, suppress windows |
| `track_faces.py` | Face track (MediaPipe) for tracked cameras: mouth row, face centre, forehead, face height |
| `timeline.py` | Frame-grid snapping, segment map, shot and state pieces, change log |
| `captions.py` | Caption file at the fixed row; engagement split per state |
| `hook.py`, `hook_chrome.py` | The hook card (PIL or Chrome-typeset) and its bottom row |
| `audio.py` | Programme audio graph and two-pass loudnorm |
| `layers.py` | Camera layers. Adapters: `tracked` (face-tracked camera + wall plate), `static` (webcam crop); `remote2.py` (remote, both people tracked), `multicam.py` + `sync.py` (in-person shared cameras), `face4k.py` (in-person, own 4K cameras) |
| `compose.py` | Engagement and clean compositor graphs, punch-in limiter |
| `gates.py` | Pre-render and render gates |
| `cli.py` | `words`, `plan`, `audio`, `render` (refuses without `--approved-export`), `verify` |
