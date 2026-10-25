"""Find active channels in a Kingst LA transition CSV."""
import csv
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else r"E:\zynqlinkPRO\results\daplink\la\manual_1ms.csv"
levels = {}
times = []
chans = None
with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
    r = csv.reader(f)
    header = next(r)
    chans = list(range(len(header) - 1))
    prev = None
    for row in r:
        if not row:
            continue
        t = float(row[0])
        vals = [int(x) for x in row[1:]]
        if prev is not None:
            for i, v in enumerate(vals):
                if v != prev[i]:
                    levels.setdefault(chans[i], []).append(t)
        prev = vals
        times.append(t)

print(f"rows={len(times)} span={times[0]*1e3:.3f}..{times[-1]*1e3:.3f} ms")
for ch in sorted(levels):
    tr = levels[ch]
    if not tr:
        continue
    # widths
    widths = [b - a for a, b in zip(tr, tr[1:])]
    widths.sort()
    print(f"CH{ch:2d}: {len(tr):8d} edges  median_dt={widths[len(widths)//2]*1e9:8.2f} ns  "
          f"p10={widths[len(widths)//10]*1e9:.2f} p90={widths[len(widths)*9//10]*1e9:.2f} ns")
