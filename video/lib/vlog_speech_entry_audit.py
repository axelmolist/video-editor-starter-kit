#!/usr/bin/env python3
"""Read-only acoustic audit of source-audio entries in an FCPXML project.

Example (run with the video's Python environment):
    python video/lib/vlog_speech_entry_audit.py --fcpxml PROJECT.fcpxmld \
        --sources sources.json --out speech-heads.json

The sources manifest is a list containing stem, path, audio_path (mono float32
16 kHz .npy) and optional transcript_path. Relative paths resolve beside the
manifest. Output is diagnostic: inspect flagged words/phonemes before editing.
VAD alone never authorises a trim or removal, and ambience remains ambience.

Speech detection comes from vlog_speech_inspector.py (Silero VAD + energy envelope); pass
the Silero ONNX model with --model. An optional external implementation can be supplied
with the VLOG_AUDIT_REFERENCE environment variable.
No source, media, manifest, episode script or FCPXML is written by this command.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
import os
REFERENCE = Path(os.environ.get('VLOG_AUDIT_REFERENCE', '/nonexistent'))
DEFAULT_MODEL = REPO / 'video/working-material/models/silero_vad.onnx'


def seconds(value: str | None, default: float = 0.0) -> float:
    return float(Fraction(value.removesuffix('s'))) if value else default


def local_path(value: str, base: Path) -> Path:
    if value.startswith('file:'):
        return Path(unquote(urlparse(value).path)).resolve()
    p = Path(value).expanduser()
    return (p if p.is_absolute() else base / p).resolve()


def load_inspector(model: Path):
    if not REFERENCE.is_file():
        from vlog_speech_inspector import make_inspector
        return make_inspector(model)
    import onnxruntime as ort
    spec = importlib.util.spec_from_file_location('_vlog_speech_entry_reference', REFERENCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load audit implementation: {REFERENCE}')
    module = importlib.util.module_from_spec(spec)
    session_factory = ort.InferenceSession

    def configured_session(_reference_path, *args, **kwargs):
        return session_factory(str(model), *args, **kwargs)

    # This CLI imports sequentially. Restore the factory even if loading fails.
    ort.InferenceSession = configured_session
    try:
        spec.loader.exec_module(module)
    finally:
        ort.InferenceSession = session_factory
    return module.inspect_head


def classify(clip: ET.Element) -> tuple[str, str]:
    keywords = ', '.join(k.get('value', '') for k in clip.findall('keyword'))
    if 'a-roll/ptc' in keywords:
        return 'ptc', keywords
    if 'sound-on speech' in keywords or 'scene dialogue' in keywords:
        return 'scene', keywords
    return 'ambience_or_unclassified', keywords


def project_clips(root: ET.Element):
    """Yield direct asset references, resolving connected-clip time coordinates."""
    projects = root.findall('.//project')
    containers = [(p.get('name', ''), p.find('sequence')) for p in projects]
    if not containers:
        containers = [('', s) for s in root.findall('./sequence')]

    def walk(parent, parent_start, parent_timeline, project, inherited_enabled=True):
        for c in parent:
            if c.tag not in {'asset-clip', 'clip', 'gap', 'ref-clip', 'mc-clip', 'sync-clip', 'video', 'audio'}:
                continue
            timeline = parent_timeline + seconds(c.get('offset'), parent_start) - parent_start
            enabled = inherited_enabled and c.get('enabled', '1') != '0'
            if c.tag in {'asset-clip', 'ref-clip', 'mc-clip'}:
                yield project, c, timeline, enabled
            yield from walk(c, seconds(c.get('start')), timeline, project, enabled)

    for name, sequence in containers:
        if sequence is not None:
            spine = sequence.find('spine')
            if spine is not None:
                yield from walk(spine, seconds(sequence.get('tcStart')), 0.0, name)


def run(args) -> dict:
    import numpy as np
    xml = args.fcpxml.expanduser().resolve()
    if xml.is_dir():
        xml /= 'Info.fcpxml'
    manifest = args.sources.expanduser().resolve()
    model = args.model.expanduser().resolve()
    for p in (xml, manifest, model):
        if not p.is_file():
            raise ValueError(f'Required file not found: {p}')
    xml_bytes = xml.read_bytes()
    root = ET.fromstring(xml_bytes)
    sources = json.loads(manifest.read_text())
    if not isinstance(sources, list):
        raise ValueError('--sources must contain a JSON list of source records')
    by_path, by_stem = {}, {}
    protected = {xml, manifest, model, REFERENCE}
    for entry in sources:
        record = dict(entry)
        for key in ('path', 'audio_path', 'transcript_path'):
            if record.get(key):
                record[key] = local_path(record[key], manifest.parent)
                protected.add(record[key])
        by_path[record['path']] = record
        by_stem.setdefault(record['stem'], []).append(record)
    output = args.out.expanduser().resolve()
    if output in protected or (output.exists() and any(p.exists() and output.samefile(p) for p in protected)):
        raise ValueError('--out must not overwrite any input, media, transcript, cache or implementation')
    inspect_head = load_inspector(model)
    assets = {a.get('id'): a for a in root.findall('./resources/asset')}
    rows, preserved, unresolved = [], [], []
    current, samples, words = None, None, []
    inspected = 0
    for index, (project, clip, timeline, enabled) in enumerate(project_clips(root)):
        if args.limit is not None and inspected >= args.limit:
            break
        aid = clip.get('ref')
        asset = assets.get(aid)
        base = dict(index=index, project=project, name=clip.get('name'), asset_ref=aid,
                    timeline_seconds=round(timeline, 6), xml_offset=clip.get('offset'))
        if clip.tag != 'asset-clip' or asset is None:
            unresolved.append({**base, 'reason': 'compound/multicam or unresolved reference; inspect its source sequence separately'})
            continue
        media = asset.find('media-rep')
        source = local_path(media.get('src'), xml.parent) if media is not None and media.get('src') else None
        start = seconds(clip.get('start')) - seconds(asset.get('start'))
        end = start + seconds(clip.get('duration'))
        kind, keywords = classify(clip)
        base.update(stem=asset.get('name', ''), source_path=str(source), source_in=round(start, 6),
                    source_out=round(end, 6), classification=kind, keywords=keywords)
        volume = clip.find('adjust-volume')
        gain = volume.get('amount', '') if volume is not None else ''
        muted_gain = gain in {'-96dB', '-inf dB', '-infdB'}
        if not enabled or clip.get('srcEnable') == 'video' or asset.get('hasAudio') == '0' or muted_gain:
            preserved.append({**base, 'reason': 'disabled or muted/video-only clip; preserve existing choice'})
            continue
        if kind == 'ambience_or_unclassified':
            preserved.append({**base, 'reason': 'no explicit PTC/scene-speech classification; preserve ambience and unclassified audio'})
            continue
        record = by_path.get(source)
        if record is None:
            choices = by_stem.get(asset.get('name', ''), [])
            if len(choices) == 1:
                record = choices[0]
        if record is None:
            unresolved.append({**base, 'source_path': str(source), 'reason': 'no unambiguous source manifest record'})
            continue
        base.update(stem=record['stem'], source_path=str(record['path']), source_in=round(start, 6),
                    source_out=round(end, 6), classification=kind, keywords=keywords)
        if current != record['stem']:
            samples = np.load(record['audio_path'], mmap_mode='r')
            if samples.ndim != 1 or not np.issubdtype(samples.dtype, np.floating):
                raise ValueError(f"Expected mono floating-point 16kHz audio: {record['audio_path']}")
            transcript = json.loads(record['transcript_path'].read_text()) if record.get('transcript_path') else {}
            words = [w for w in transcript.get('words', []) if w.get('type', 'word') == 'word'
                     and w.get('end', 0) > w.get('start', 0)]
            current = record['stem']
        if start < 0 or end <= start or start >= len(samples) / 16000:
            unresolved.append({**base, 'reason': 'source range outside decoded audio'})
            continue
        try:
            metrics = inspect_head(samples, start, end, words)
        except (ValueError, IndexError) as exc:
            unresolved.append({**base, 'reason': f'cannot measure source head: {exc}'})
            continue
        inspected += 1
        row = {**base, **metrics, 'status': 'clear', 'suspicious': False}
        onset = metrics['onset']
        if not words or record.get('peak_db', 0) < -65:
            row.update(status='speech_unestablished', reason='preserve existing audio; VAD alone is insufficient evidence')
        elif onset is None or onset >= end - .05:
            row.update(status='review_unresolved_speech', suspicious=True,
                       reason='no confirmed syllable before picture end; inspect waveform, words and natural sound before any removal')
        elif onset - start > .04 + 1e-6:
            proposed = math.ceil((onset - .04) * 25 - 1e-7) / 25
            row.update(status='review_lead_over_one_frame', suspicious=True,
                       proposed_picture_source_in=proposed,
                       reason='energy plus speech detector suggest >40ms lead; verify first consonant and retained words manually')
            first = metrics.get('first_word')
            if first and proposed > first['end'] + .04:
                row.update(status='review_possible_word_loss',
                           reason='candidate crosses a complete ASR word; never apply without independent phonetic review')
        rows.append(row)
    return dict(input_fcpxml=str(xml), input_sha256=hashlib.sha256(xml_bytes).hexdigest(),
                sources_manifest=str(manifest), model=str(model), implementation_reference=str(REFERENCE if REFERENCE.is_file() else Path(__file__).with_name('vlog_speech_inspector.py')),
                read_only=True, sample_rate=16000, review_threshold_seconds=.04,
                limitation='Diagnostic only. No listening validation. Compound/multicam references are reported unresolved; unclassified audio is preserved.',
                summary=dict(inspected_speech_heads=inspected, suspicious_heads=sum(r['suspicious'] for r in rows),
                             preserved_clips=len(preserved), unresolved_clips=len(unresolved),
                             statuses=dict(Counter(r['status'] for r in rows)), limit=args.limit),
                suspicious_heads=[r for r in rows if r['suspicious']], inspected_heads=rows,
                preserved_clips=preserved, unresolved_clips=unresolved)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fcpxml', type=Path, required=True, help='FCPXML file or .fcpxmld bundle')
    parser.add_argument('--sources', type=Path, required=True, help='Source audio/transcript manifest JSON')
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL, help='Local Silero ONNX model')
    parser.add_argument('--out', type=Path, required=True, help='Diagnostic JSON output; cannot overwrite an input')
    parser.add_argument('--limit', type=int, help='Maximum number of classified speech heads to measure')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    try:
        result = run(args)
        args.out.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.out.expanduser().resolve().write_text(json.dumps(result, indent=2) + '\n')
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as exc:
        print(f'Audit failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result['summary'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
