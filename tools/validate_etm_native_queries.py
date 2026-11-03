"""Compare native query DTOs with the retained Python reader, offline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'etm-service/tools'))
import native_core
import native_storebuild
import trace_store


def first_difference(a, b, path='$'):
    if type(a) is not type(b) and not isinstance(a, (int, float)):
        return path, a, b
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return path + '.keys', sorted(a), sorted(b)
        for key in a:
            result = first_difference(a[key], b[key], path + '.' + key)
            if result:
                return result
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return path + '.length', len(a), len(b)
        for i, (x, y) in enumerate(zip(a, b)):
            result = first_difference(x, y, path + '[%d]' % i)
            if result:
                return result
    elif a != b:
        return path, a, b
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--binary', type=Path)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    folder = a.record.resolve()
    if not (folder / 'manifest.json').is_file():
        folder /= 'store'
    if a.binary:
        native_storebuild.binary_path = lambda root=None: a.binary.resolve()
    rng = random.Random(0xD023)
    checks = []
    before = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
    started = time.perf_counter()
    with trace_store.TraceStore(folder) as reference, native_core.Store(folder) as native:
        last = reference.last_seq
        def check(method, *args, **kwargs):
            try:
                expected = getattr(reference, method)(*args, **kwargs)
            except ValueError:
                try:
                    getattr(native, method)(*args, **kwargs)
                except ValueError:
                    checks.append(dict(method=method, args=args, kwargs=kwargs, bothRejected=True))
                    return
                raise AssertionError(('native accepted invalid query', method, args, kwargs))
            actual = getattr(native, method)(*args, **kwargs)
            difference = first_difference(expected, actual)
            descriptor = dict(method=method, args=args, kwargs=kwargs)
            if difference:
                (a.out / 'failure.json').write_text(json.dumps(dict(case=descriptor,
                    difference=difference, expected=expected, actual=actual),
                    ensure_ascii=False, indent=2) + '\n', encoding='utf8')
                raise AssertionError((descriptor, difference))
            encoded = json.dumps(actual, ensure_ascii=False, sort_keys=True).encode('utf8')
            checks.append(dict(**descriptor, sha256=hashlib.sha256(encoded).hexdigest()))
        check('overview')
        check('stats')
        points = sorted(set([0, 1, 2, last, max(0, last - 1), 4095, 4096, 4097]
                            + [rng.randrange(last + 1) for _ in range(24)]))
        for seq in points:
            if seq <= last:
                check('event', seq)
                check('seq_position', seq)
        for params in [dict(), dict(offset=999999999), dict(start=913, end=977),
                       dict(start=4090, end=4200, hide_skipped=True), dict(start=0, end=-1, search='cdc'),
                       dict(search='cdc', limit=17, offset=33), dict(search='no-such-code'),
                       dict(search='PC', hide_skipped=True), dict(view='packets', offset=1024, limit=23),
                       dict(view='packets', search='a-sync', limit=3)]:
            check('page', **params)
        windows = [(0, 0, 100), (0, min(last, 150), 100), (913, min(last, 977), 1200),
                   (4090, min(last, 9001), 160), (max(0, last - 20), last, 1200), (0, last, 1200)]
        for _ in range(15):
            lo = rng.randrange(last + 1)
            windows.append((lo, min(last, lo + rng.choice([1, 33, 300, 8191, 100001])), rng.choice([100, 200, 1200])))
        for lo, hi, bins in windows:
            if lo <= hi:
                check('window', lo, hi, bins)
        for lo, hi in [(0, 0), (0, min(150, last)), (913, min(977, last)), (4090, min(12000, last)), (0, last)]:
            if lo <= hi:
                check('function_timeline', lo, hi, bins=240)
                if hi - lo < 50000:
                    check('function_timeline', lo, hi, search='cdc', hide_skipped=True, bins=300, max_functions=3)
        for seq in [0, min(913, last), last // 2, last]:
            for mode in ('instruction', 'call', 'return', 'exception', 'issue', 'source'):
                for direction in (-1, 1):
                    check('navigate', seq, direction, mode)
            for pc in [reference.static[0].pc, reference.static[-1].pc, 0xFFFFFFFF]:
                for direction in (-1, 1):
                    check('navigate', seq, direction, 'instruction', pc, 0, last)
        for offset in [0, 17, max(0, len(reference.issues_list) - 1), len(reference.issues_list) + 1]:
            check('issues', offset, 100)
        fields = ('pc','size','bytes','mnemonic','operands','function','file','line','flow','conditional','predicated')
        assert [tuple(getattr(v,k) for k in fields) for v in native.static] == [tuple(getattr(v,k) for k in fields) for v in reference.static]
        assert native.strings == reference.strings and native.sources == reference.sources
    assert hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest() == before
    result = dict(ok=True, offline=True, record=str(a.record.resolve()), checks=checks,
                  queryCount=len(checks), manifestUnchanged=True,
                  validationWallSeconds=time.perf_counter() - started,
                  note='Functional checks, not a performance benchmark; deep DTO equality and stable response digests')
    (a.out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Native query full DTO differential: PASS', len(checks), flush=True)


if __name__ == '__main__':
    main()
