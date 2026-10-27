# B-roll-to-music montage standard

Applies to every beat-cut b-roll sequence set to music, in any format: vlog hook montages and b-roll blocks,
long-form montage sections, and personal or event montages.

## Rule 1 - Use every supplied clip (BLOCKING)

When the creator hands over footage, **every clip appears in the cut at least once**. They prune later; the agent never
pre-filters. "Too dark", "just a sign", "near-duplicate" are not reasons to omit: those are what the strobe slots are
for (below). The only exception is a genuinely broken file (a 0-1 s accidental recording), and even that is flagged in
the edit summary, never silently dropped.

## Rule 2 - Beat sync must survive into the deliverable (BLOCKING)

Cutting on a measured beat grid is necessary but not sufficient. The classic failure: cuts frame-locked to a correct
grid, a preview rendered through a separate ffmpeg audio path (in sync), but the FCPXML placed the music ~1 s early, so
in Final Cut every cut was off-beat.

1. **Measure the grid properly.** Beat-track the actual file (librosa); check half/double-time ambiguity (a 172 BPM
   detection is usually an 86 BPM feel); find the drop/chorus with an energy profile, not by assumption.
2. **FCPXML anchored-offset law.** A connected clip's `offset` is in the PARENT clip's source-time coordinates, NOT
   sequence time. To place music at timeline T under a parent at timeline `p_off` with source-in `p_start`:
   `offset = p_start + (T - p_off)`. `video/lib/vlog_build.py` implements this.
3. **QC the deliverable's maths, not a parallel path.** Verify music-vs-cut alignment with the same placement
   arithmetic the deliverable uses.
4. Frame-exact segment renders: cut by frame counts (`-frames:v`), never float `-t` (floats drop frames and the concat
   drifts through fast sections).

## The strobe cold open and bookend

- **Cold open:** ~1-1.5 s of 2-frame flicker cuts sampling the piece's best details, BEFORE the music starts, with a
  click SFX on every cut and a riser underneath; the music enters as the first real scene lands. It hooks, teases, and
  is the natural home for leftover clips (Rule 1's remainder bin).
- **Bookend echo:** the same strobe run (3-frame this time) just before the final hold, then the tail shot plays out
  and fades.
- The usual sparse-SFX rule is suspended inside the strobe only.

## Pacing

- **Ramp, don't tour.** 4-beat establishing -> 2-beat -> 1-beat -> half-beat frenzy. In a sub-2-minute montage, **no
  low-energy breather section**: a short montage keeps climbing.
- **Land the payoff early enough to enjoy it** (it may take the last third of the runtime).
- **Decelerate INTO the ending:** holds lengthen through the payoff (~1.8 s -> 3.5 s -> a ~6 s final hold), then the
  strobe echo, then the tail with the fade.
- **Keep the complete first beat.** Trim only verified silence before its full onset; never cut at a detector peak
  inside the attack. Start the music under the first real scene, not under the cold open.
- People get held cuts (about 2x the surrounding pace); objects and details get the fast cuts.
- Loose is fine, off is not: within ~2 frames of the beat reads as on-beat; a constant phase error reads as arrhythmic.
