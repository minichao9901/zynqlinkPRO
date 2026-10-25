"""Stream a huge Kingst CSV, find an active SWCLK window, and write a small slice."""
import csv
import sys
from pathlib import Path

src = Path(sys.argv[1])
out = Path(sys.argv[2])
max_lines = int(sys.argv[3]) if len(sys.argv) > 3 else 5_000_000
win_ms = 2.0

buckets = {}
prev = None
rows = []
with src.open(newline="", encoding="utf-8-sig", errors="replace") as f:
    r = csv.reader(f)
    next(r)
    for i, row in enumerate(r):
        if i >= max_lines:
            break
        t = float(row[0])
        v0 = int(row[1])
        if prev is not None and v0 != prev:
            b = int(t * 1000)
            buckets[b] = buckets.get(b, 0) + 1
        prev = v0
        rows.append((t, row))

print(f"scanned rows={len(rows)} t_end={rows[-1][0]*1e3:.2f} ms")
top = sorted(buckets.items(), key=lambda kv: -kv[1])[:8]
print("transition buckets (ms -> edges):", top)

if not top:
    sys.exit("no edges found")

best = top[0][0]
t0 = best / 1000.0
t1 = t0 + win_ms / 1000.0
sel = [row for t, row in rows if t0 <= t <= t1]
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Time[s]"] + [f"CH{i}" for i in range(16)])
    # initial state: last row before t0
    before = [row for t, row in rows if t < t0]
    if before:
        w.writerow(before[-1])
    for row in sel:
        w.writerow(row)
print(f"wrote {out} rows={len(sel)} window={t0*1e3:.3f}..{t1*1e3:.3f} ms size={out.stat().st_size}")
