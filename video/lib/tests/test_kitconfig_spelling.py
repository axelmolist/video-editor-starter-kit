#!/usr/bin/env python3
"""Config merge and locale dispatch. Run: python3 video/lib/tests/test_kitconfig_spelling.py (or pytest)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import kitconfig  # noqa: E402
import spelling  # noqa: E402


def test_style_merges_brand():
    s = kitconfig.style()
    for role in ("background", "primary", "accent", "text", "muted"):
        assert s["palette"][role].startswith("#")
    assert s["output"]["fps"] > 0 and s["captions"]["font"]


def test_ass_bgr():
    assert kitconfig.ass_bgr("#112233") == "332211"


def test_locale_dispatch():
    os.environ["KIT_LOCALE"] = "en-GB"
    assert spelling.to_locale("the color of the organization") == "the colour of the organisation"
    os.environ["KIT_LOCALE"] = "en-US"
    assert spelling.to_locale("the color of the organization") == "the color of the organization"
    del os.environ["KIT_LOCALE"]


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
    print("ok")
