# video/instructions/animations/ - animation spec, by format

Pipeline: `animation-locator` (finds the beats) -> `diagram-designer` (specs each one) -> `animation-generator` (builds
and renders). Engine per `config/brand.json` `animation.default_engine`: Remotion (`remotion/`) or HyperFrames
(`design-studio/`, `video/lib/templates/`). Rules: `../brand-video-guardrails.md` and `../style-config.json` `animations`.

Per-format differences:
- **shorts** - less room; snappy, nothing static for more than ~1 s; full-screen blur takeovers for the biggest beats.
- **youtube-long** - more room; section cards, lower thirds, stat cards, receipts.
- **podcast shorts** - the top-panel animation track, one comp spanning the whole short (see the podcast shorts spec).
- **podcast episodes** - usually none over the body; an intro sting or lower thirds for names at most.
