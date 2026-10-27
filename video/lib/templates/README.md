# templates

Worked examples the `animation-generator` follows when the HyperFrames (HTML/CSS) engine is chosen.

- **`build-scenes.example.py`** - generates one HTML/CSS HyperFrames composition per beat from a
  shared CSS head built from `config/brand.json`: fonts via `@font-face src: local(...)` (NEVER
  `url(file://)` - it silently falls back to serif), palette roles, title font for titles. Each
  scene is **one continuous motion** that climaxes on the beat's key word, ~2-4s.
- **`compose.example.sh`** - composites the rendered scenes onto the UNCUT source: each scene
  faded in 0.2s / out 0.3s and placed so its climax lands the key word, then captions burned
  last. Caption `fontsdir` must be a CLEAN font dir - libass tries to load every file in it.

These are reference patterns, not a fixed library. The generator authors a per-video version
(different beats, different timings). Rules live in `../../instructions/brand-video-guardrails.md`
and `../../instructions/style-config.json`.
