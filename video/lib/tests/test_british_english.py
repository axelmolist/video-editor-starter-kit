#!/usr/bin/env python3
"""Tests for video/lib/british_english.py. Run: python3 video/lib/tests/test_british_english.py (or pytest)."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from british_english import to_british, normalise_words, normalise_transcript_file, find_americanisms  # noqa: E402

LIB = os.path.dirname(HERE)


def eq(us, gb):
    got = to_british(us)
    assert got == gb, f"{us!r} -> {got!r}, expected {gb!r}"


def test_ize_case_and_inflections():
    eq("realize", "realise"); eq("Realize", "Realise"); eq("REALIZE", "REALISE")
    eq("realized", "realised"); eq("realizing", "realising"); eq("realizes", "realises")
    eq("But then I realized that", "But then I realised that")
    eq("organization", "organisation"); eq("organizations", "organisations"); eq("Organizations", "Organisations")
    eq("the organization's goals", "the organisation's goals")
    eq("optimizer", "optimiser"); eq("recognizable", "recognisable"); eq("prioritize,", "prioritise,")
    eq("monetized.", "monetised."); eq("customizing?", "customising?")


def test_yze():
    eq("analyze", "analyse"); eq("analyzed", "analysed"); eq("analyzing", "analysing"); eq("analyzer", "analyser")
    eq("paralyzed", "paralysed"); eq("catalyze", "catalyse")


def test_or_our():
    eq("color", "colour"); eq("colors", "colours"); eq("colored", "coloured"); eq("colorful", "colourful")
    eq("behavior", "behaviour"); eq("behaviors", "behaviours"); eq("behavioral", "behavioural")
    eq("favorite", "favourite"); eq("favorites", "favourites"); eq("favorable", "favourable")
    eq("neighborhood", "neighbourhood"); eq("honorable", "honourable"); eq("colorist", "colourist")
    eq("colorize", "colourise")


def test_or_same_in_both():
    for w in ["humorous", "honorary", "laborious", "vigorous", "humorist", "humoral", "odorous"]:
        eq(w, w)


def test_er_re():
    eq("center", "centre"); eq("centered", "centred"); eq("centers", "centres"); eq("Center the text", "Centre the text")
    eq("theater", "theatre"); eq("fiber", "fibre"); eq("kilometers", "kilometres")


def test_misc():
    eq("defense", "defence"); eq("offense", "offence")
    eq("traveling", "travelling"); eq("traveled", "travelled"); eq("canceled", "cancelled"); eq("labeled", "labelled")
    eq("catalog", "catalogue"); eq("catalogs", "catalogues"); eq("gray", "grey"); eq("grayscale", "greyscale")
    eq("mom", "mum"); eq("My mom said", "My mum said"); eq("Mom", "Mum"); eq("moms", "mums")
    eq("judgment", "judgement"); eq("fulfillment", "fulfilment"); eq("enrollment", "enrolment")
    eq("practicing", "practising"); eq("skeptical", "sceptical"); eq("aluminum", "aluminium")


def test_punctuation_preserved():
    eq('"Realize," he said - color!', '"Realise," he said - colour!')
    eq("(organize)", "(organise)"); eq("color-coded", "colour-coded")


def test_ize_exceptions():
    for w in ["size", "sizes", "sized", "resize", "downsizing", "oversized", "capsize", "capsized", "prize", "prizes",
              "seize", "seized", "seizes", "maize", "baize", "Belize", "citizen", "citizens", "Zeiss", "wizard",
              "quizzes", "denizen", "kaizen", "spritzer", "lizard", "pizza"]:
        eq(w, w)


def test_context_dependent_skipped():
    for w in ["program", "programs", "check", "tire", "license", "practice", "meter", "dialog", "draft", "artifact",
              "gotten", "percent", "toward", "learned"]:
        eq(w, w)


def test_proper_nouns_and_products():
    for t in ["Center Parcs", "OpenAI", "Final Cut Pro", "Anthropic", "Claude", "HighLevel", "GoHighLevel",
              "Color Board", "Pearl Harbor", "Labor Day", "Lincoln Center", "World Health Organization",
              "ElevenLabs", "Macy Gray"]:
        eq(t, t)
    eq("We went to Center Parcs and saw the color", "We went to Center Parcs and saw the colour")


def test_urls_handles_code():
    for t in ["https://example.com/organize-color", "www.colorize.io", "@colorlab", "#realize", "`colorize()`",
              "Math.round", "color_grade.py", "video/lib/colorize.py", "gpt4color", "x=color"]:
        eq(t, t)
    eq("see example.com/organize and realize it", "see example.com/organize and realise it")


def test_ass_markup():
    eq(r"{\fs78\1c&H5757FF&}realized{\fs70}", r"{\fs78\1c&H5757FF&}realised{\fs70}")
    eq(r"I realize\Nthe color", r"I realise\Nthe colour")
    eq("{asking Claude} to organize", "{asking Claude} to organise")


def test_normalise_words_keeps_timings():
    words = [
        {"text": "But", "start": 1.0, "end": 1.2, "type": "word", "speaker_id": "s0", "logprob": -0.1},
        {"text": " ", "start": 1.2, "end": 1.21, "type": "spacing"},
        {"text": "I", "start": 1.21, "end": 1.3, "type": "word"},
        {"text": " ", "start": 1.3, "end": 1.31, "type": "spacing"},
        {"text": "realized,", "start": 1.31, "end": 1.9, "type": "word"},
        {"text": " ", "start": 1.9, "end": 1.91, "type": "spacing"},
        {"text": "Center", "start": 1.91, "end": 2.2, "type": "word"},
        {"text": " ", "start": 2.2, "end": 2.21, "type": "spacing"},
        {"text": "Parcs", "start": 2.21, "end": 2.6, "type": "word"},
    ]
    before = json.dumps(words)
    out = normalise_words(words)
    assert json.dumps(words) == before, "input mutated"
    assert [w["text"] for w in out] == ["But", " ", "I", " ", "realised,", " ", "Center", " ", "Parcs"]
    for a, b in zip(words, out):
        assert {k: v for k, v in a.items() if k != "text"} == {k: v for k, v in b.items() if k != "text"}
    # no spacing items (some pipelines strip them)
    out2 = normalise_words([{"text": "colour"}, {"text": "color"}, {"word": "x"}])
    assert out2[1]["text"] == "colour" and out2[2] == {"word": "x"}
    # custom key
    assert normalise_words([{"w": "organize", "start": 0}], key="w")[0] == {"w": "organise", "start": 0}


def test_transcript_file_json_and_txt():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.json")
    json.dump({"language_code": "eng", "text": "I realize the color",
               "words": [{"text": "I", "start": 0, "end": 0.1, "type": "word"},
                         {"text": " ", "start": 0.1, "end": 0.1, "type": "spacing"},
                         {"text": "realize", "start": 0.1, "end": 0.5, "type": "word"}]}, open(p, "w"))
    q = normalise_transcript_file(p, os.path.join(d, "out.json"))
    o = json.load(open(q))
    assert o["text"] == "I realise the colour" and o["words"][2]["text"] == "realise"
    assert o["words"][2]["start"] == 0.1 and o["language_code"] == "eng"
    t = os.path.join(d, "m.txt"); open(t, "w").write("[12.34-15.67] S0 we analyzed 75% of it\n")
    normalise_transcript_file(t)
    assert open(t).read() == "[12.34-15.67] S0 we analysed 75% of it\n"


def test_find_and_cli_check():
    assert find_americanisms("realize the color of size") == [("realize", "realise"), ("color", "colour")]
    d = tempfile.mkdtemp(); p = os.path.join(d, "a.txt"); open(p, "w").write("I realized it.\n")
    r = subprocess.run([sys.executable, os.path.join(LIB, "british_english.py"), p, "--check"], capture_output=True,
                       text=True)
    assert r.returncode == 1 and "realized -> realised" in r.stdout, r.stdout
    open(p, "w").write("I realised it.\n")
    r = subprocess.run([sys.executable, os.path.join(LIB, "british_english.py"), p, "--check"], capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stdout
    r = subprocess.run([sys.executable, os.path.join(LIB, "british_english.py"), "-"], input="analyze color",
                       capture_output=True, text=True)
    assert r.stdout == "analyse colour"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as e:
                fails += 1; print(f"FAIL {name}: {e}")
    print(f"{'OK' if not fails else f'{fails} FAILED'}")
    sys.exit(1 if fails else 0)
