"""Replay an immutable ETM input through binary and direct C++ paths, serially."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'etm-service/tools'))
import decode_stream
from trace_cli import engine_environment
from compare_etm_stores import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--truncate', type=int, default=0)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--tracker-diff', action='store_true')
    group.add_argument('--buffered-diff', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    record = args.record.resolve()
    original = json.loads((record / 'decoded.json').read_text(encoding='utf8'))
    source = record / 'etm.bin'
    if not source.exists():
        source = record / 'capture.bin'
    raw = source.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    if args.truncate:
        assert 0 < args.truncate < len(raw)
        raw = raw[:-args.truncate]
    engine_environment()
    rows = []
    modes = [('rescan', '1', '1', '0'), ('replay', '1', '1', '1')] if args.buffered_diff else [('independent', '1', '0', '1'), ('shared', '1', '1', '1')] if args.tracker_diff else [('binary', '0', '1', '0'), ('direct', '1', '1', '1')]
    for name, enabled, shared, buffered in modes:
        os.environ['ETM_DIRECT_DECODE'] = enabled
        os.environ['ETM_SHARED_TRACKER'] = shared
        os.environ['ETM_BUFFERED_DECODE'] = buffered
        folder = (args.out / name).resolve()
        folder.mkdir()
        for filename in ['firmware.elf', 'sources.json', 'session.json']:
            if (record / filename).exists():
                shutil.copy2(record / filename, folder / filename)
        start = time.perf_counter()
        decoded = decode_stream.decode_stream(raw, folder / 'firmware.elf', folder,
            config=original['config'], sources=json.loads((folder / 'sources.json').read_text(encoding='utf8')),
            framing=original.get('framing'), physical=original.get('physical'),
            capture=original.get('capture'))
        rows.append(dict(engine=name, tracker=shared, buffered=buffered, seconds=time.perf_counter() - start,
                         summary=decoded['summary'], quality=decoded['quality']))
        if enabled == '1':
            assert not (folder / 'native.bin').exists()
    assert rows[0]['summary'] == rows[1]['summary']
    assert rows[0]['quality'] == rows[1]['quality']
    result = compare(args.out / modes[0][0] / 'store', args.out / modes[1][0] / 'store')
    result.update(rows=rows, inputSha256=hashlib.sha256(raw).hexdigest(),
                  originalSha256=source_sha, truncate=args.truncate, offline=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
    (args.out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Full offline differential replay: PASS', [(r['engine'], round(r['seconds'], 3)) for r in rows])


if __name__ == '__main__':
    main()
