# design-studio

HTML/CSS stills (and, if you chose HyperFrames, HTML/CSS animations) rendered with
[HyperFrames](https://www.npmjs.com/package/hyperframes), a headless-Chromium HTML capture tool.
Remotion (`/remotion`) is the default for animation; this folder is for PNG stills such as
thumbnails, quote cards, title cards and carousels, plus HTML animation if you prefer it.

## How it works

1. `python3 scripts/apply_brand.py` writes `brand.css` (palette and font CSS variables) and
   `fonts-embedded.css` (your font files as base64 data URIs) from `config/brand.json`.
2. `design-system.css` is the render layer: backdrop, render-scale headings, accent devices.
   It uses only the variables, never a literal colour or font.
3. Copy a template from `templates/` into your project folder and edit `index.html`. A still is a
   single frame (`data-duration="0.04"`); an animated card is one continuous GSAP motion (~2-4 s)
   on a paused `window.__timelines["main"]`.
4. Render: `./design-studio/render.sh still <project-dir> <out.png>` (or `video` / `alpha`).
   HyperFrames needs Node 22+ and ffmpeg/ffprobe on PATH.

Sizes: set `data-width`/`data-height` and the `html/body/#root` sizes together. Common ones:
1080x1080, 1080x1350, 1080x1920, 1280x720 (thumbnail), 1200x630 (OG image). For 4K, author at 2x.

## Gotchas (each one cost a real render)

- **PNG sequences render with alpha.** `html`/`body` backgrounds are dropped, so a dark design comes
  out transparent. Paint the backdrop on an in-DOM element: `<div class="ds-bg"></div>` first in `#root`.
- **Fonts must be inlined.** HyperFrames captures a still before linked webfonts load, so a `url()`
  `@font-face` bakes the fallback font into the PNG. Link `fonts-embedded.css` LAST. Never use
  `url(file://...)`: it silently falls back to a serif. `.ttc` collections cannot be embedded; for
  those, install the font on the system and rely on the `local("<exact face name>")` rules in `brand.css`.
- **Register the real weights.** A single Regular `@font-face` renders bold text thin, because
  `font-weight` has no real face to use. Give the bold file in `config/brand.json` (`bold_file`).
- **Link all stylesheets, in order:** `brand.css`, `design-system.css`, `fonts-embedded.css`.
  HyperFrames does not follow `@import` inside a linked file.
- **Counters:** HyperFrames captures by seeking, so `onUpdate` callbacks that mutate text freeze.
  Use transform/opacity tweens, or follow HyperFrames' own counter pattern, and check the climax frame.
- **Verify the font actually rendered**: change a weight and confirm the output visibly changes.
