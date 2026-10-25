"""Focus on the largest SWD burst: per-word timing and gaps."""
import csv
import sys

import numpy as np

path = sys.argv[1] if len(sys.argv) > 1 else r"E:\zynqlinkPRO\results\daplink\la\manual_1ms.csv"
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
dt = np.diff(rt)

frames = []
s = 0
for i, g in enumerate(dt):
    if g > 40:
        frames.append((s, i, rt[s], rt[i], i - s + 1))
        s = i + 1
frames.append((s, len(rt) - 1, rt[s], rt[-1], len(rt) - s))
print("frames", len(frames))

# largest gap-separated groups
gaps = np.array([frames[i + 1][2] - frames[i][3] for i in range(len(frames) - 1)])
big = gaps > 500
starts = np.concatenate(([0], np.where(big)[0] + 1))
ends = np.concatenate((np.where(big)[0], [len(frames) - 1]))
groups = [(s, e, frames[e][3] - frames[s][2], e - s + 1) for s, e in zip(starts, ends)]
groups.sort(key=lambda x: -x[3])
print("top groups by frame count:")
for s, e, dur, n in groups[:6]:
    print(f"  frames={n:5d} dur={dur/1000:8.2f} us  start={frames[s][2]/1000:.3f} ms")

s, e, dur, n = groups[0]
print(f"\nlargest group: frames={n} dur={dur/1000:.2f} us")
starts_t = np.array([frames[k][2] for k in range(s, e + 1)])
lens = np.array([frames[k][4] for k in range(s, e + 1)])
per = np.diff(starts_t)
print("per-frame start interval ns: median=%.1f p10=%.1f p90=%.1f min=%.1f max=%.1f"
      % (np.median(per), np.percentile(per, 10), np.percentile(per, 90), per.min(), per.max()))
print("clocks/frame within group: median=%d p10=%d p90=%d" % (np.median(lens), np.percentile(lens, 10), np.percentile(lens, 90)))
print("frame duration ns: median=%.1f" % np.median([frames[k][3] - frames[k][2] for k in range(s, e + 1)]))
fg = [frames[k + 1][2] - frames[k][3] for k in range(s, e)]
print("intra-group gaps ns: median=%.1f p10=%.1f p90=%.1f max=%.1f"
      % (np.median(fg), np.percentile(fg, 10), np.percentile(fg, 90), max(fg)))
print("first 10 frame clock counts:", lens[:10].tolist())
print("first 10 frame gaps:", [round(x, 1) for x in fg[:10]])
