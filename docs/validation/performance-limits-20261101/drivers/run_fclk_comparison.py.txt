"""Sequential Golden/release 50/60MHz comparison; no hardware parallelism."""
import argparse
from pathlib import Path
import subprocess
import sys

from validate_fclk_performance import ROOT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--pairs', default='golden,release')
    a = p.parse_args()
    for pair in a.pairs.split(','):
        for phase in ['load', 'swd', 'jtag']:
            subprocess.run([sys.executable, str(ROOT / 'tools/validate_fclk_performance.py'),
                            '--pair', pair, '--out', str(a.out / pair), '--phase', phase],
                           cwd=ROOT, check=True)
        subprocess.run([sys.executable, str(ROOT / 'tools/validate_fclk_edge_cases.py'),
                        '--pair', pair, '--out', str(a.out / (pair + '-trace')),
                        '--kind', 'trace-rtt'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
