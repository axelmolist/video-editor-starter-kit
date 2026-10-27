#!/usr/bin/env python3
"""Tests for video/lib/caption_dedupe.py. Run: python3 video/lib/tests/test_caption_dedupe.py (or pytest)."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from caption_dedupe import find_overlaps, gate, norm, load_captions, captions_from_ass  # noqa: E402

LIB = os.path.dirname(HERE)
CAPS = [
    {"start": 10.9, "end": 12.0, "text": "then I can go in"},
    {"start": 12.0, "end": 14.0, "text": "and do the {final tweaks}."},
    {"start": 20.0, "end": 22.0, "text": "we cut costs by 75 per cent"},
    {"start": 30.0, "end": 31.5, "text": "But then I realized"},
    {"start": 31.5, "end": 33.0, "text": "it was a project"},
]


def test_norm():
    assert norm("Final Tweaks!") == "final tweaks"
    assert norm("75 per cent") == "75%" and norm("75 percent") == "75%" and norm("75%") == "75%"
    assert norm("I Realized") == "i realised"
    assert norm(r"{\fs78\1c&H5757FF&}Don't{\fs70} stop") == "dont stop"
    assert norm("£1,000.50 now.") == "1000.50 now"


def test_run_match_final_tweaks():
    ov = find_overlaps(CAPS, [{"id": "A3", "start": 10.9, "end": 14.05, "text": "Final tweaks"}])
    assert len(ov) == 1 and ov[0]["anim_id"] == "A3" and ov[0]["matched"] == "final tweaks" and ov[0]["rule"] == "run"


def test_number_contained():
    ov = find_overlaps(CAPS, [{"id": "n", "start": 20.5, "end": 21.0, "text": "75%"}])
    assert len(ov) == 1 and ov[0]["rule"] == "contained" and ov[0]["matched"] == "75%"


def test_single_word_contained_and_short_word_ignored():
    ov = find_overlaps(CAPS, [{"id": "p", "start": 31.6, "end": 32.5, "text": "Project"}])
    assert len(ov) == 1 and ov[0]["matched"] == "project"
    assert find_overlaps(CAPS, [{"id": "w", "start": 31.6, "end": 32.5, "text": "was"}]) == []


def test_british_spelling_both_sides():
    ov = find_overlaps(CAPS, [{"id": "r", "start": 30.0, "end": 31.0, "text": "Then I realised"}])
    assert len(ov) == 1 and ov[0]["matched"] == "then i realised"


def test_time_window_respected():
    # same text but far away in time -> no overlap
    assert find_overlaps(CAPS, [{"id": "A3", "start": 40.0, "end": 42.0, "text": "Final tweaks"}]) == []
    # inside the pad -> overlap
    assert len(find_overlaps(CAPS, [{"id": "A3", "start": 14.3, "end": 15.0, "text": "Final tweaks"}])) == 1
    assert find_overlaps(CAPS, [{"id": "A3", "start": 14.3, "end": 15.0, "text": "Final tweaks"}], window_pad=0.1) == []


def test_stopword_only_runs_ignored():
    assert find_overlaps(CAPS, [{"id": "s", "start": 11.0, "end": 13.0, "text": "and do the"}]) == []


def test_run_across_two_captions():
    ov = find_overlaps(CAPS, [{"id": "x", "start": 30.0, "end": 33.0, "text": "realized it was"}])
    assert len(ov) == 1 and ov[0]["matched"] == "realised it was"


def test_rewritten_text_passes():
    anims = [{"id": "A3", "start": 10.9, "end": 14.05, "text": "Human finish"},
             {"id": "A1", "start": 1.3, "end": 4.7, "text": "MP4"}]
    assert find_overlaps(CAPS, anims) == []
    assert gate(CAPS, anims) == 0
    assert gate(CAPS, [{"start": 10.9, "end": 14.05, "text": "final tweaks"}]) == 1


def test_min_words_param_and_multiline():
    ov = find_overlaps(CAPS, [{"id": "m", "start": 12.0, "end": 13.0, "text": "Human\nfinal tweaks"}])
    assert len(ov) == 1 and ov[0]["anim_text"] == "final tweaks"
    assert find_overlaps(CAPS, [{"id": "m", "start": 12.0, "end": 13.0, "text": "final tweaks"}], min_words=3) == []


def test_ass_loader_and_cli():
    ass = ("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
           r"Dialogue: 0,0:00:12.00,0:00:14.00,Cap,,0,0,0,,{\pos(542.5,965)\blur6}and do the final tweaks" + "\n"
           r"Dialogue: 1,0:00:12.00,0:00:14.00,Cap,,0,0,0,,{\pos(540,960)}and do the {\fs78}final tweaks{\fs70}" + "\n")
    caps = captions_from_ass(ass)
    assert len(caps) == 1 and caps[0]["start"] == 12.0 and caps[0]["text"] == "and do the final tweaks"
    d = tempfile.mkdtemp()
    cp, ap = os.path.join(d, "c.ass"), os.path.join(d, "a.json")
    open(cp, "w").write(ass)
    json.dump({"anim_texts": [{"id": "A3", "start": 11.0, "end": 14.0, "text": "Final tweaks"}]}, open(ap, "w"))
    assert len(load_captions(cp)) == 1
    r = subprocess.run([sys.executable, os.path.join(LIB, "caption_dedupe.py"), cp, ap], capture_output=True, text=True)
    assert r.returncode == 1 and "A3" in r.stdout, r.stdout
    json.dump([{"id": "A3", "start": 11.0, "end": 14.0, "text": "Human finish"}], open(ap, "w"))
    r = subprocess.run([sys.executable, os.path.join(LIB, "caption_dedupe.py"), cp, ap], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    # podcast cue shape [text, start, end] and SRT
    sp = os.path.join(d, "c.srt")
    open(sp, "w").write("1\n00:00:12,000 --> 00:00:14,000\nand do the final tweaks\n\n")
    assert load_captions(sp)[0]["end"] == 14.0
    jp = os.path.join(d, "c.json"); json.dump({"cues": [["final tweaks", 12.0, 14.0]]}, open(jp, "w"))
    assert load_captions(jp)[0]["text"] == "final tweaks"


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
