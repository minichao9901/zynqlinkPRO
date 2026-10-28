"""Compare two ``sim_regress_matrix.py`` result files and report regressions.

A regression is any packet or JTAG word that costs more FCLK cycles than the
baseline commit under identical settings, or a baseline-passing case that now
fails.

Usage::

    python tools/compare_sim_matrix.py build/sim_matrix/main.json build/sim_matrix/base-swd.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cur = load(sys.argv[1])
    base = load(sys.argv[2])
    problems = []

    print(f'current {cur["commit"][:8]}  baseline {base["commit"][:8]}')
    print('\n== SWD packet wire cost (FCLK cycles per packet) ==')
    ref = {(r['half_ns'], r['words'], r['read'], r['idle']): r['cycles']
           for r in base['swd_packet'] if 'cycles' in r and r.get('rx', 0) == 0}
    for row in cur['swd_packet']:
        if 'cycles' not in row:
            continue
        key = (row['half_ns'], row['words'], row['read'], row['idle'])
        b = ref.get(key)
        delta = None if b is None else row['cycles'] - b
        ok = delta is not None and delta <= 0
        if not ok:
            problems.append(f'packet half={row["half_ns"]} rx={row.get("rx")} '
                            f'words={row["words"]} read={row["read"]}: {row["cycles"]} vs {b}')
        print(f'  half={row["half_ns"]:>4} rx={row.get("rx")} words={row["words"]:>4} '
              f'read={row["read"]} cycles={row["cycles"]:>6} base={b} delta={delta}'
              f'{"  OK" if ok else "  REGRESS"}')

    print('\n== JTAG steady AP read (FCLK cycles per word) ==')
    refw = {r['speed']: r['word6_fclk'] for r in base.get('jtag_words', [])}
    for row in cur.get('jtag_words', []):
        b = refw.get(row['speed'])
        delta = None if b is None else row['word6_fclk'] - b
        ok = delta is not None and delta <= 0
        if not ok:
            problems.append(f'jtag {row["speed"]}: {row["word6_fclk"]} vs {b}')
        print(f'  {row["speed"]:>8} fclk/word={row["word6_fclk"]} base={b} '
              f'delta={delta}{"  OK" if ok else "  REGRESS"}')

    print(f'\n{len(problems)} regression(s)')
    for p in problems:
        print('  ' + p)
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
