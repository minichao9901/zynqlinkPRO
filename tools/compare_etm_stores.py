"""Compare complete execution blocks and query tables of two offline stores."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'etm-service/tools'))
import numpy as np
import trace_store as ts


def compare(expected, actual):
    result = dict(blocks={}, tables=[])
    with ts.TraceStore(expected) as left, ts.TraceStore(actual) as right:
        assert left.counts == right.counts, 'store counts differ'
        assert left.summary.get('analysis') == right.summary.get('analysis'), 'complete analysis differs'
        # Static instructions, strings, complete execution stream, packets,
        # navigation and boundaries: every byte is compared, not sampled.
        for kind in (1, 2, 3, 4, 5, 6, 11):
            a = left.container.of_type(kind)
            b = right.container.of_type(kind)
            assert len(a) == len(b), ('block counts', kind)
            digests = []
            for x, y in zip(a, b):
                payload = left.container.block(x)
                assert payload == right.container.block(y), ('block content', kind, x, y)
                digests.append(dict(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()))
            result['blocks'][str(kind)] = digests
        assert left.issues_list == right.issues_list, 'quality issues differ'
        names = left.query_index.arrays._archive.files
        assert set(names) == set(right.query_index.arrays._archive.files)
        for name in names:
            if name == 'meta_json':
                continue  # generation/build timings are deliberately different
            a, b = left.query_index.arrays[name], right.query_index.arrays[name]
            assert a.dtype == b.dtype and a.shape == b.shape, ('table layout', name)
            assert np.array_equal(a, b), ('table content', name)
            result['tables'].append(name)
    result['ok'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--actual', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.expected, args.actual)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Complete execution blocks, issues and %d query tables: PASS' % len(result['tables']))


if __name__ == '__main__':
    main()
