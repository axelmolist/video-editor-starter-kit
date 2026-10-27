# In-person podcast microphone switching

Applies to every in-person show and every isolated mic, including extra hosts and co-hosts.

Keep the speaking participant's mic open. Completely mute inactive mics so their room pickup and delayed spill do not produce echo. Use fast 0.01-second opening and closing ramps: exactly 480 samples at 48 kHz. Keep this timing on the audio sample clock; do not round a ramp to a video frame.

Derive mic activity from each isolated recording, its local energy and its own transcript. Camera selection is not an audio gate: a wide shot, listener reaction or minimum camera dwell must not close the person speaking. Identify the person on each mic from the recording; filenames do not establish identities. Analyse every supplied mic separately without mixed-track diarisation.

Retain both mics when both people speak. Protect short responses, laughter, quiet onsets and trailing consonants. Use conservative source handles around detected speech; if a quiet sound could be dialogue, keep it. Compare secondary-mic energy with room spill and independently spoken words before deciding that it is active. Never mute a word merely because another speaker is louder. Check representative interruptions and backchannels against source audio.

For Final Cut projects, keep the original isolated audio clips continuous, in their original synchronisation. Apply source-clock volume keyframes and complete mute plateaus between the ramps. Preserve intentional existing manual mutes. Do not chop the conversation into physical audio clips or change the episode pacing to implement microphone switching.

Validate all ramps at 0.01 seconds, every mic's complete source coverage, source and timeline sync, overlap protection and the Final Cut import. Retain an editable gate audit with open ranges and the detection method. Revise the same project when requested; do not create a new version just to add mic automation.

Project edits and internal audio assets are permitted. Export a video only with the creator's explicit export go-ahead.
