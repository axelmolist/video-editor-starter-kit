#!/usr/bin/env python3
"""One place every script reads its settings from.

    config/brand.json                     who you are: names, palette, fonts, logos, locale (written by /setup)
    video/instructions/style-config.json  how videos are built: output sizes, captions, grade, animation rules

Palette colours are referred to by ROLE (background, primary, accent, text, muted), never by name, so a
brand change is a config change and never a code change. Until /setup has run, config/brand.example.json is
used so tests and dry runs still work; scripts that render real output call require_setup() first.
"""
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("KIT_ROOT", Path(__file__).resolve().parents[2]))
VIDEO = ROOT / "video"
CONFIG = ROOT / "config"
STYLE_PATH = VIDEO / "instructions" / "style-config.json"
BRAND_PATH = CONFIG / "brand.json"
BRAND_EXAMPLE = CONFIG / "brand.example.json"
SETUP_DONE = CONFIG / ".setup-complete"


def _load(p):
    with open(p) as f:
        return json.load(f)


def brand():
    return _load(BRAND_PATH if BRAND_PATH.exists() else BRAND_EXAMPLE)


def style():
    s = _load(STYLE_PATH)
    b = brand()
    s["palette"] = b["palette"]
    s.setdefault("output", {}).update(b.get("output", {}))
    s.setdefault("captions", {}).setdefault("font", b["fonts"]["captions"]["name"])
    s["captions"].setdefault("font_file", b["fonts"]["captions"].get("file", ""))
    g = s.setdefault("graphics", {})
    g.setdefault("title_font", b["fonts"]["title"]["name"])
    g.setdefault("title_font_file", b["fonts"]["title"].get("file", ""))
    g.setdefault("label_font", b["fonts"]["body"]["name"])
    g.setdefault("label_font_file", b["fonts"]["body"].get("file", ""))
    return s


def palette():
    return brand()["palette"]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def locale():
    return brand().get("locale", "en-US")


def font_file(role):
    """Absolute path of the font file for 'title', 'body' or 'captions' (relative paths resolve from the repo root)."""
    f = brand()["fonts"][role].get("file", "")
    if not f:
        return ""
    p = Path(os.path.expanduser(f))
    return str(p if p.is_absolute() else ROOT / p)


def path(key):
    """A folder from brand.json "paths" (raw_footage, broll_library, music, sfx, projects), expanded."""
    v = brand().get("paths", {}).get(key, "")
    if not v:
        return None
    p = Path(os.path.expanduser(v))
    return p if p.is_absolute() else ROOT / p


def require_setup():
    if not (BRAND_PATH.exists() and SETUP_DONE.exists()):
        raise SystemExit("Setup has not run. Open the repo in Claude Code and type /setup first.")


def ass_bgr(h):
    """'#RRGGBB' -> 'BBGGRR', the order ASS/libass colour tags use (e.g. \\1c&HBBGGRR&)."""
    h = h.lstrip("#").upper()
    return h[4:6] + h[2:4] + h[0:2]
