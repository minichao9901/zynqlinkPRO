"""Compare the retained Python index/finalizer with the complete C++ builder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback
from contextlib import ExitStack
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'etm-service/tools'))
from compare_etm_stores import compare


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--truncate', type=int, default=0)
    parser.add_argument('--reference-binary', type=Path)
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = args.record.resolve()
    original = json.loads((record / 'decoded.json').read_text(encoding='utf8'))
    source = record / ('etm.bin' if (record / 'etm.bin').exists() else 'capture.bin')
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if args.truncate:
        assert 0 < args.truncate < len(raw)
        raw = raw[:-args.truncate]
    from trace_cli import engine_environment
    import native_storebuild
    import decode_stream
    engine_environment()
    original_binary_path = native_storebuild.binary_path
    rows = []
    try:
        for name, mode in [('reference', '0'), ('cpp', '1')]:
            os.environ['ETM_COMPLETE_INDEX'] = mode
            os.environ['ETM_DIRECT_DECODE'] = '1'
            os.environ['ETM_BUFFERED_DECODE'] = '1'
            native_storebuild.binary_path = (lambda root=None: args.reference_binary.resolve()) if name == 'reference' and args.reference_binary else original_binary_path
            folder = output / name
            folder.mkdir()
            for filename in ('firmware.elf', 'sources.json', 'session.json'):
                if (record / filename).exists():
                    shutil.copy2(record / filename, folder / filename)
            (folder / 'capture.bin').write_bytes(raw)
            start = time.perf_counter()
            with ExitStack() as guard:
                if mode == '1':
                    import native_facts_index
                    import trace_store
                    def forbidden(*args, **kwargs):
                        raise AssertionError('Complete C++ mode entered the Python facts/index/store writer')
                    for attribute in ('read_facts_any', 'read_index_facts', 'build_full_index'):
                        guard.enter_context(patch.object(native_facts_index, attribute, forbidden))
                    guard.enter_context(patch.object(trace_store._BlockSink, 'assemble', forbidden))
                decoded = decode_stream.decode_stream(raw, folder / 'firmware.elf', folder,
                    config=original['config'], sources=json.loads((folder / 'sources.json').read_text(encoding='utf8')),
                    framing=original.get('framing'), physical=original.get('physical'), capture=original.get('capture'))
            row = dict(engine=name, seconds=time.perf_counter() - start,
                       summary=decoded['summary'], quality=decoded['quality'],
                       performance=decoded['performance'])
            rows.append(row)
            save(output / (name + '-result.json'), row)
            if mode == '1':
                manifest = json.loads((folder / 'store/manifest.json').read_text(encoding='utf8'))
                assert manifest['queryIndex']['builtBy'] == 'native-complete-index'
                assert manifest['engine']['buildCosts']['scratchFactsWritten'] is False
                assert not any(p.name in ('facts.bin', 'index-facts.bin', 'native.bin', 'publish.payload') for p in folder.rglob('*'))
        assert rows[0]['summary'] == rows[1]['summary'], 'summary differs'
        assert rows[0]['quality'] == rows[1]['quality'], 'quality differs'
        result = compare(output / 'reference/store', output / 'cpp/store')
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        result.update(rows=rows, sourceRecord=str(record), sourceInputSha256=digest,
                      decodedInputSha256=hashlib.sha256(raw).hexdigest(), truncate=args.truncate,
                      originalUnchanged=True, offline=True)
        save(output / 'result.json', result)
        print('Full C++ index/store differential: PASS', [(r['engine'], round(r['seconds'], 3)) for r in rows])
    except BaseException as error:
        save(output / 'failure.json', dict(error=str(error), traceback=traceback.format_exc(), rows=rows))
        raise
    finally:
        native_storebuild.binary_path = original_binary_path


if __name__ == '__main__':
    main()
