---
name: youtube-vlog
description: Plans and edits vlog episodes (travel, day-in-the-life, behind-the-scenes) from a pile of rushes into an editable Final Cut project and, on request, a finished file - spine-first story, a beat-cut hook montage, PTC/B-roll loop, day/time stamps, music under b-roll only, subtitles for noisy or non-English speech, and a matte vlog grade via colour-grader. Also briefs the creator BEFORE they film. Use for "plan my vlog", "edit vlog episode 3", "string out these rushes".
tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

# youtube-vlog

## Read first
`config/brand.json`, `brand/voice.md`, `video/instructions/brand-video-guardrails.md`,
`video/instructions/broll-music-montage-standard.md`, `video/lib/VLOG-EDITING-TOOLS.md`, `guides/hook-frame-counting.md`.
If `config/.setup-complete` is missing, stop and ask for `/setup`.

## 0. The cardinal rule: a spine, not a journey

"Documenting the journey" is a container, not a spine. A spine is **a question that gets answered or a bet that
resolves**. Without one you have a montage with narration and no reason to reach minute nine.

Every episode gets **one question, agreed before filming.** A good spine: the creator genuinely does not know the
answer when filming starts; the stakes are real, never manufactured; the place or life element is the test, not the
decoration. **Make the bet measurable** (state on camera what has to get done, and count it off at the end).

Reject spines with a predictable answer, false binaries, or ones the footage cannot answer. In the intro keep the
objection; cut the self-reassurance that answers the question before the video starts.

**The cut test:** every scene, interview and piece to camera (PTC) must help the spine, make it stronger, or be
something the video pays off later. If not, it goes, however good it is on its own. Long conversations are cut to
their arc (setup, confession, challenge, answer), not their highlights.

## 1. Structure

1. **Hook** - the state the creator is actually in. No runway, no "hey guys".
2. **Context** - what is at stake and what else they are carrying.
3. **Tension** - the work happens anyway; something breaks or slips.
4. **Pivot** - the moment something gets cut, deferred or cracks. Cannot be scheduled; without it the ending is flat.
5. **Payoff** - the honest answer at the end, including "I got this wrong".

But/therefore, never and-then. Length is earned, never filled.

## 2. Assembly grammar

```
Silent cold open (~0.5 s, the first frame is already a shot)
  -> HOOK: beat-cut montage WITH music (~45-75 s)
  -> intro PTC carrying the spine (1-2 min, dry after the music hand-off)
  -> B-roll block (30 s - 1 min) -> PTC -> B-roll block -> PTC ... -> the payoff PTC
```

- **Music lives on B-roll, the hook and transitions. Never audible full-spectrum music under someone speaking.**
  Hand-off into a PTC: start a linear low-pass sweep ~2 s before the dialogue, keep fading through the first ~5 s of
  speech, then the PTC is dry.
- **B-roll audio modes:** (1) no music, natural clip audio up; (2) music with the natural audio ducked/low-passed
  under it; (3) music only, clip audio muted; (4) B-roll over a PTC's voice, no music, and RELEVANT to what is said.
  Never a silent clip with no music and no clip audio.
- **J-cut into every sound-on entry:** the incoming audio leads its picture by ~0.5 s.
- **Music enters on its first beat, complete attack, no fade-in.** Filters and fades take music OUT, never in.
- **Hook montage:** alternate subject shots (the creator doing things, not talking) with scenery; open on two long
  holds, settle into ~2-beat cuts, tighten to 1-beat cuts as a title builds word by word; land the title on a music
  breakdown; resolve on one impressive thing in fast cuts, then a wider hold. Never repeat a framing back to back.
  Full rules: `broll-music-montage-standard.md` (use every supplied clip; beat sync must survive into the FCPXML).

## 3. Editing rules (blocking)

- **PTC joins: pause after A, ~0.1 s before B.** Finish A's last word and hold a brief natural pause; start B about
  0.1 s before its first spoken sound. Never cut A sharp and leave the waiting at B's start. Measure both sides on the
  waveform. Run `video/lib/vlog_speech_entry_audit.py` on the delivered FCPXML and resolve every flag.
- **Never eat into audio.** Protect quiet consonants, breathy onsets and trailing sounds. If unsure, keep it.
- **Real option-T micro crossfades at every adjacent audio edit:** audio extended ~0.02 s each side, 1-frame
  (0.04 s) fades that cross. A fade-out then fade-in pumps the room tone. Longer fades are audible.
- **All audio processing stays editable** in Final Cut: reference the original audio and use native effects,
  keyframes and fade handles. Never bake gain, EQ or ducking into generated WAVs.
- **Compressor** (Final Cut's stock one, default settings) on every PTC clip.
- **Cut on complete points.** Let the creator set the point up AND make it, on camera. Never cut away to B-roll on
  the punchline.
- **PTC compression is an intake question:** none / light (fillers, clear repetition) / medium (also redundant setup
  and tangents) / aggressive (fewest usable words). Unanswered = preserve PTCs in full and offer a pass later.
- **Strict capture-time chronology.** Order shots by when they were filmed (day folder = date authority; camera
  clocks and filename order for sequence; distrust a camera's date if known wrong but keep its relative order). The
  only allowed shifts: B-roll over a voice, and one signposted flash-forward in the hook.
- **Steady B-roll only.** Use the still sections of a clip; discard clips under 10 s that move throughout. Measure
  camera movement (phase correlation), do not guess.
- **Clip audio only when someone is visibly talking**; announcements, sat-navs, TV and off-screen voices are muted.
- **No two similar B-roll shots adjacent; never repeat a clip; never repeat a music composition in one episode.**
- **Body B-roll is phrase-aware and beat-locked:** a real mix of 4- and 2-beat holds; 1-beat cuts only inside a
  measured rise. Quantise each boundary to the absolute beat grid so rounding never accumulates.
- **Day and time stamps:** open every new day, and every distinct scene, with its day/time (and location) bottom left,
  revealing ~1.5 s into its clip and holding ~5 s across clip boundaries, with a click SFX on the reveal.
- **Subtitles** for noisy backgrounds, distant or unclear speech, and every non-English exchange (translated). Check
  each phrase's language with forced decodes; short-phrase language ID silently mistranslates. A clean quiet PTC gets
  none. Style per `config/brand.json` captions, bottom centre, as native editable titles.
- **The most honest piece to camera is the centrepiece.** Transcribe EVERY camera, including action cams; keep it
  substantially whole, no music.
- **Frame-exact renders:** every shot renders to an exact frame count and all audio is placed from those counts.

## 4. The grade

Delegate to `colour-grader`. A vlog look that travels well is a **sandy matte split tone**: warm mids and highlights,
neutral or slightly cool shadows (warm everything goes sepia); lift only the toe (blacks ~6-10) with an S through the
middle (lifting everything goes washed out); saturation slightly muted (~0.92-0.98). Check skin (R > G ≈ B). Add light
grain after the grade (`noise=alls=6:allf=t+u`); if it shows on skin, it is too much. Match what the creator wants.

## 5. Edit order: never face the footage as one blob

1. **Dump only** while travelling: one folder per date.
2. **Selects log**, not an edit: transcribe everything, log the timecodes where something happens or something true
   is said. An agent job.
3. **The ugly string-out:** selected PTCs and voice memos only, in spine order. No B-roll, music, grade or titles.
   Watching it is the only reliable answer to "is there a film in this". If the spine is not answered, stop here.
4. Only then: B-roll over the string-out, shot matching, grade, grain, graphics and captions last.

## 6. Build pipeline and review points

Every stage ends in an editable Final Cut project (FCPXML, media in place). **(R)** = the creator reviews and you stop.

| # | Stage | Output |
|---|---|---|
| 0 | Spine + bet before filming; a filming brief **(R)** | `SPINE.md` |
| 1 | Footage into `raw-footage/` per camera **(R)** | - |
| 2 | Intake: inventory, camera clocks, transcribe every camera, selects log; the PTC-compression question **(R)** | `editor-files/` |
| 3 | Skeleton / string-out in spine order | skeleton FCPXML |
| 4 | The creator's first edit in Final Cut **(R)** | their FCPXML |
| 5 | Story tighten from their timeline: cut what does not serve the spine, compress PTCs, crossfades, both sides of every join checked **(R)** | long cut vN + `EDIT-NOTES.md` |
| 6 | Story lock and the hook montage **(R)** | their FCPXML |
| 7 | Finishing pass, in one go: music, beat-cut B-roll, ducking under speech, levels, stamps + clicks, subtitles | vNext FCPXML |
| 8 | Review rounds: change only what was asked **(R)** | vN+1 |
| 9 | Packaging: title, thumbnail options, description, chapters (written with whoever owns the brand voice) **(R)** | `PACKAGING.md` |
| 10 | Grade, grain, export: by the creator, or rendered on their explicit go-ahead | the movie |

Revisions always start from the creator's current timeline: diff it, keep their work frame-exact, and preserve
unaffected material.

## 7. Before filming: the brief

Agree the spine and the bet. Remind them to: record every opportunity (rushes are cheap); film a short piece to
camera at each turning point and at the end of each day; capture steady B-roll of places, hands, screens and people;
keep one mic per speaker when possible; and dump footage nightly into one folder per date without judging it.

## 8. Music

If generated music is used (e.g. the ElevenLabs Music API), never name real artists in prompts; describe genre, BPM,
instrumentation and mood, and end with "start with the beat instantly, no ramp up". Keep a small set of cue types by
purpose (standard b-roll, movement, high-energy, adventure) in `brand/voice.md` once the creator has chosen them.
