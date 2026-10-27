# Vlog editing tools

Implementation references for the `youtube-vlog` agent. No tool exit status substitutes for listening to a retained
phrase or reviewing both sides of a cut. Never rerun a builder over the creator's current project without an
editing request.

| Tool | Purpose | Limit |
| --- | --- | --- |
| `fcpxml_audio.py` | Adds native source-audio overlaps (micro crossfades) and checks adjacent audible joins. Typical handles are 20 ms with 40 ms fades. | Valid overlap does not prove a complete consonant or a correct pause. Check source bounds and the whole retained envelope. |
| `vlog_build.py` | EDL -> FCPXML skeleton builder (original media, native audio, beat-anchored music placement). | Check the anchored-offset law (`broll-music-montage-standard.md`) on every music placement. |
| `vlog_speech_entry_audit.py` | Reads FCPXML and a source-audio manifest; writes a diagnostic report of spoken entries. | Entry analysis, not a complete head-and-tail audit. A clean exit does not mean every entry is safe. |
| `vlog_speech_inspector.py` | Silero VAD and energy-envelope inspector used by the audit. | Quiet speech can escape VAD or energy thresholds. Neither detector authorises a trim. |

The speech audit takes `--fcpxml`, `--sources`, `--model` and `--out`. Download the Silero VAD ONNX model
(github.com/snakers4/silero-vad) and pass its path, or place it at `video/working-material/models/silero_vad.onnx`.
The manifest (see the script docstring) points to mono 16 kHz NumPy audio and optional transcripts. Dependencies:
NumPy, SciPy and onnxruntime.

When revising a project the creator has edited: preserve resource definitions and unaffected subtrees, ripple
connected material with its parent, and compare the union of original source-audio intervals, fade handles included.
