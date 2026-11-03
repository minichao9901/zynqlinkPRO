"""Offline reader latency, including native process/IPC and identical DTO work."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'etm-service/tools'))
import native_core
import trace_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--repeat', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20:
        parser.error('repeat must be 1..20')
    folder = args.record.resolve()
    if folder.name != 'store':
        folder /= 'store'
    before = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
    result = dict(offline=True, record=str(folder), manifestSha256=before, repeat=args.repeat,
        scope='Same retained store; cold application reader (OS cache not flushed), then repeated warm calls. Native timings include IPC and DTO conversion. No HTTP/browser/acquisition.', readers=[])
    for name, reader in [('python-reference', trace_store.TraceStore), ('cpp', native_core.Store)]:
        started = time.perf_counter()
        store = reader(folder)
        row = dict(engine=name, openSeconds=time.perf_counter() - started, queries={})
        try:
            mid = (store.first_seq + store.last_seq) // 2
            cases = [('overview', lambda: store.overview()),
                     ('page', lambda: store.page(offset=mid, limit=150)),
                     ('page-filter', lambda: store.page(search='cdc', offset=0, limit=150)),
                     ('window-default', lambda: store.window()),
                     ('window-partial', lambda: store.window(max(0, mid-12000), min(store.last_seq, mid+12000), bins=800)),
                     ('timeline-default', lambda: store.function_timeline()),
                     ('timeline-partial', lambda: store.function_timeline(max(0, mid-12000), min(store.last_seq, mid+12000), bins=300)),
                     ('navigate-call', lambda: store.navigate(mid, 1, 'call'))]
            for operation, call in cases:
                samples = []
                for _ in range(args.repeat):
                    started = time.perf_counter()
                    value = call()
                    samples.append(time.perf_counter() - started)
                digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
                row['queries'][operation] = dict(seconds=samples, medianSeconds=statistics.median(samples), dtoSha256=digest)
        finally:
            store.close()
        result['readers'].append(row)
    for operation in result['readers'][0]['queries']:
        assert result['readers'][0]['queries'][operation]['dtoSha256'] == result['readers'][1]['queries'][operation]['dtoSha256'], operation
    assert hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest() == before
    result['dtoDigestsMatch'] = result['manifestUnchanged'] = True
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print('Native query latency and DTO verification: PASS', args.out, flush=True)


if __name__ == '__main__':
    main()
