"""Print sampled SWDIO bits per frame for the first N frames."""
import csv
import sys

import numpy as np

path = sys.argv[1] if len(sys.argv) > 1 else r"E:\zynqlinkPRO\results\daplink\la\manual_1ms.csv"
n_show = int(sys.argv[2]) if len(sys.argv) > 2 else 12
times, levels = [], []
with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
    r = csv.reader(f)
    header = next(r)
    for row in r:
        if row:
            times.append(float(row[0]))
            levels.append([int(x) for x in row[1:]])
t = np.array(times) * 1e9
lv = np.array(levels, dtype=np.int8)
clk, dio = lv[:, 0], lv[:, 1]
rise = np.where((clk[1:] == 1) & (clk[:-1] == 0))[0] + 1
rt = t[rise]
dio_i = np.searchsorted(t, rt, side="right") - 1
bits_all = "".join(str(int(x)) for x in dio[dio_i])

frames = []
s = 0
for i in range(len(rt) - 1):
    if rt[i + 1] - rt[i] > 40:
        frames.append((s, i))
        s = i + 1
frames.append((s, len(rt) - 1))

for k, (a, b) in enumerate(frames[:n_show]):
    bits = bits_all[a:b + 1]
    print(f"frame {k:2d}: {b - a + 1:3d} clocks  t={rt[a]/1000:8.3f}us  bits={bits}")

# also decode SWD request for the 45-clock frames
print("\n45-clock frames (full transactions):")
count = 0
for k, (a, b) in enumerate(frames):
    n = b - a + 1
    if n >= 44 and count < 8:
        bits = bits_all[a:b + 1]
        start = bits[0]
        apndp, rnw, a2, a3, par, stop, park = [int(x) for x in bits[1:8]]
        print(f"  frame {k}: start={start} APnDP={apndp} RnW={rnw} A={a2}{a3} par={par} stop={stop} park={park}")
        count += 1
