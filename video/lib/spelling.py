#!/usr/bin/env python3
"""Spelling normaliser driven by config/brand.json "locale".

ElevenLabs Scribe only takes a bare language code ("en"), so English transcripts come back in American
spelling whatever the speaker's accent. Normalise on our side, after transcription, at the point words become
caption or on-screen text.

    en-GB, en-AU, en-NZ, en-IE, en-ZA  -> British spelling (british_english.py)
    anything else                      -> unchanged (Scribe already writes American English)

To support another variant, add a module with the same four functions and register it in _ENGINES.

API:
    to_locale(text) -> str
    normalise_words(words, key="text") -> list[dict]     # Scribe word lists, timings untouched
    normalise_transcript_file(path_in, path_out=None) -> str
    find_off_locale(text) -> list[(found, wanted)]       # for --check gates
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kitconfig  # noqa: E402

_BRITISH = {"en-GB", "en-AU", "en-NZ", "en-IE", "en-ZA"}


def _engine():
    loc = os.environ.get("KIT_LOCALE") or kitconfig.locale()
    if loc in _BRITISH:
        import british_english as be
        return be.to_british, be.normalise_words, be.normalise_transcript_file, be.find_americanisms
    return None


def to_locale(text):
    e = _engine()
    return e[0](text) if e else text


def normalise_words(words, key="text"):
    e = _engine()
    return e[1](words, key=key) if e else words


def normalise_transcript_file(path_in, path_out=None):
    e = _engine()
    if e:
        return e[2](path_in, path_out)
    raw = open(path_in).read()
    if path_out:
        open(path_out, "w").write(raw)
    return raw


def find_off_locale(text):
    e = _engine()
    return e[3](text) if e else []


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Normalise a transcript or caption file to the configured locale.")
    ap.add_argument("file"); ap.add_argument("--check", action="store_true"); ap.add_argument("-o", dest="out")
    a = ap.parse_args()
    if a.check:
        bad = find_off_locale(open(a.file).read())
        for f, w in bad:
            print(f"{f} -> {w}")
        sys.exit(1 if bad else 0)
    out = normalise_transcript_file(a.file, a.out)
    if not a.out:
        print(out)
