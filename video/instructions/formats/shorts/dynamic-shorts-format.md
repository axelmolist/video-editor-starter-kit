# Dynamic shorts format

For **scroll-stopping shorts**, both clipped from a long-form master and shot raw: **something changes on screen every
2-3 seconds**, and every change is purposeful, on-brand and elegant. Dynamic, not overdone. Built by `shorts-editor`;
this file is the spec, the agent file is the procedure.

## 1. Hard constraints

- Output at the house vertical resolution and fps (`config/brand.json` `output`); verify with ffprobe.
- Brand values only from `config/brand.json` (via `remotion/src/brand.ts` and `kitconfig.py`). No literal colours.
- No emoji. No em dashes in on-screen text. Spelling in the configured locale.
- Never cut mid-word; cuts land on silence detected in the audio, not on transcript times.
- Stop at finished files: never upload, never schedule.
- **Never reuse the same animation twice in one short**, and vary the primitive across a batch.
- ONE takeover moment per ~15-20 s. If everything shouts, nothing does.
- **Snappy: never static for more than ~1 s.** A graphic that must stay up longer keeps progressing (phrase by phrase)
  or is dropped.
- Phone fill-crop safe zone: see `CLEAN-STYLE.md` (x 14%-86%, nothing above 12%).

## 2. Base framing

From a landscape master, the vertical base is a 9:16 crop centred on the face, head in the **upper third** (eyes at
~0.28-0.33 of the height). That leaves headroom for chips (M2) and the lower ~45% for captions and panels (M3).

Punch-in rhythm: alternate the base crop (100%) and a punch-in (~112-115%) **on sentence boundaries**, holding each for
at least a full sentence. Implement per concat segment (each segment carries its own crop), never as a mid-segment drift.

If the master has **baked landscape graphics or b-roll**, never crop them vertically: avoid that window or cover it with
a native vertical graphic. Detect them with scene-cut detection (`select='gt(scene,0.3)'`) plus a dense contact sheet:
a talking-head master has near-zero hard cuts, so each detected cut marks an insert. If covering with blur, verify the
text underneath is genuinely unreadable (big type survives gblur sigma 40).

## 3. Layout modes

Every second is in exactly one mode. A 45-60 s short uses M1 as its spine plus 3-5 beats from M2-M5.

- **M1 - Talking head.** Base crop, live captions. The default between beats.
- **M2 - Floating chips.** Small on-brand elements in the headroom (a 2-4 word label, a mini counter, an app icon,
  a pairing). Spring in (scale 0.6 -> 1.0, ~350 ms), hold while the sentence lands, fade ~300 ms. Max ~2 at once.
- **M3 - Split screen.** The speaker in the top half; the bottom half carries a purpose-built panel (counter, gauge,
  timeline, bars) or, best of all, **real footage or a screen recording**. Re-measure the top-half crop on real frames
  (a full-frame crop clips the head once squeezed into a half). A bottom panel must keep moving while it is up.
  **Use real assets, not filler:** if the master contains a baked screen recording, lift it into the bottom half and time
  its key moment to the matching word.
- **M4 - Blur takeover.** The live frame blurred (gblur sigma ~40, little or no darkening: heavy tint looks dirty),
  captions suppressed, one big word or short phrase at a time, centred, landing on the spoken words. Text-only takeovers
  read premium; a card floating on blur reads cheap. Reserve for the 1-2 biggest moments.
- **M5 - Quote / receipt card.** Quote in large type, attribution in muted text. Every named quote is attributed
  accurately; a factual claim's source goes on screen here.
- **M6 - Insert.** A real screen recording, photo or clip, full-bleed or in a device frame. Only when a real asset exists.
- **Generated b-roll** only if `generated_media.allow_ai_broll` is true in `config/brand.json`. It is off by default
  because AI filler tends to read as cheap; where no real asset exists, carry the line with the talking head, a
  punch-in, a chip or a text-only takeover.

## 4. Typography, transitions and captions

- Emphasis words may use a second display face if your brand has one (load each face under its own family name in
  Remotion so CSS can never fake a style). In libass, emphasis is more reliable as a **size bump + accent colour** than
  an inline font switch.
- **Flash transition:** a short white flash (4 frames up, 4 down, peak ~85%) on split/takeover entry boundaries. Never
  two within ~1.5 s.
- **Captions:** 2-4 words per cue from Scribe word times remapped onto the cut; caption font with Bold=0 (libass
  italic-fallback fix); no outline; a two-layer drop shadow (soft near-black back layer ~72% alpha, sharp front);
  centred below the face; ~58-72 px at 1080x1920 PlayRes; pop-in `\fscx72\fscy72` -> 100 over ~130 ms. At most one
  accent word per cue; bump it ~1.5x. Suppress captions inside every M4 window.
- **Spelling patch:** Scribe mishears names. Keep a per-channel table of correct spellings (product names, people,
  your domain) in `brand/voice.md` and apply it to every on-screen string.

## 5. Story shape and CTA

- Hook by second 3, tension, pivot, payoff. The clip must work with zero context and end on a strong line.
- Splicing two non-adjacent windows (setup + payoff) is allowed when the join reads as a deliberate jump cut.
- Clipped shorts have no spoken CTA, so the CTA is a small on-screen end overlay in the last ~2 s.

## 6. Pipeline (per short)

1. **Transcript.** Reuse the master's Scribe JSON if it exists; otherwise transcribe.
2. **Clip and cut.** Silence-cut inside the chosen windows (`silencedetect` noise -35 dB, min 0.35-0.5 s), lead 0.05 /
   tail 0.15. Keep sentences whole. Write `edl.json` with per-segment `{src_in, src_out, crop}`.
3. **Storyboard** `beats.md`: cut time -> mode -> what the graphic shows -> exact climax word. Check restraint rules first.
4. **Base render** in one ffmpeg pass: per-segment crop, scale, fps, 25 ms audio fades, concat, H.264 CRF 18.
5. **Graphics** in Remotion (`remotion/src/jobs/<slug>.tsx`, comps at 1080x1920, registered in `src/jobs/index.ts`).
   Render overlays with alpha: `--codec=prores --prores-profile=4444 --pixel-format=yuva444p10le` (the pixel format
   is what keeps transparency; verify `yuva444p10le` with ffprobe).
6. **Composite** overlays on the base; build M4 from a blurred branch switched in for the window.
7. **Captions** (`video/lib/captions.py`), dedupe gate (`caption_dedupe.py`), burn last.
8. **End CTA** overlay in the last 2 s.
9. **QC:** a 1 fps contact sheet you actually read; listen to every boundary; ffprobe; spelling table; size cap
   (`fit_under_size.py`).
10. **Stop.** Present the file and the beat sheet for approval.

## 7. Taste

- One idea per graphic, generous space, brand palette only, springs that settle, confident type.
- If a beat's graphic cannot be explained in one sentence, it is too complicated: cut it.
- When in doubt between adding a graphic and leaving the delivery alone, leave it alone.
