# podcast_episode

Scripts for a full multicam podcast episode, used by the `podcast-editor` agent.

| Script | Role |
|---|---|
| `build_edl.py` | Multicam switching EDL from per-mic activity (body is never pacing-cut) |
| `render.py` | Render the episode cut from `edl.json`, frame-locked, verify every segment |
| `hook_words.py` | Print every hook word with its hook-local time |
| `gen_hook_captions.py` | Template for high-energy hook captions (copy per episode) |
| `build_hook.py` | Hook clips + captions -> intro jingle -> episode cut, stream-copied |
| `pick_frames.py`, `make_cutouts.py`, `trim_arm.py`, `make_thumbnail.py` | Thumbnail: best frames, B&W cut-outs (rembg), boom-arm trim, the 1280x720 card |

Expected episode folder (`video/projects/podcasts/<show>/<episode>/raw-footage/`): `double-shot-4k.mov`,
`host-shot-4k.mov`, `guest-shot-4k.mov`, and one isolated wav per mic (`host-audio.wav`, `guest-audio.wav`, ...).

**Note:** `build_edl.py`, `render.py` and `hook_words.py` read a mixed `full-audio.wav` and its transcript. Make it as
a working mixdown of the per-mic wavs (`ffmpeg -i host-audio.wav -i guest-audio.wav -filter_complex amix=inputs=2
full-audio.wav`), but always take speaker attribution from the per-mic transcripts, never from diarising the mix.

The thumbnail scripts need a separate venv with `rembg`, `opencv-python` and `pillow`.
