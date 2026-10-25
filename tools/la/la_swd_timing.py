"""SWD timing analysis from a Kingst LA transition CSV.

Reconstructs SWCLK/SWDIO, measures clock period, per-transaction clocks,
inter-transaction gaps and burst (USB packet) boundaries.
"""
import argparse
import csv
from collections import Counter

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--clk", type=int, default=0)
    ap.add_argument("--dio", type=int, default=1)
    ap.add_argument("--gap-ns", type=float, default=40.0, help="clock gap that starts a new frame")
    ap.add_argument("--burst-ns", type=float, default=500.0, help="gap that separates bursts")
    args = ap.parse_args()

    times, levels = [], []
    with open(args.csv, newline="", encoding="utf-8-sig", errors="replace") as f:
        r = csv.reader(f)
        header = next(r)
        nch = len(header) - 1
        for row in r:
            if not row:
                continue
            times.append(float(row[0]))
            levels.append([int(x) for x in row[1:]])
    t = np.array(times) * 1e9  # ns
    lv = np.array(levels, dtype=np.int8)
    print(f"rows={len(t)} span={t[0]:.1f}..{t[-1]:.1f} ns")

    clk = lv[:, args.clk]
    dio = lv[:, args.dio]

    # rising edges of clk (level after row i)
    rise = np.where((clk[1:] == 1) & (clk[:-1] == 0))[0] + 1
    print(f"clk rising edges={len(rise)}")

    # sample dio at each rising edge using last transition <= time
    dio_idx = np.searchsorted(t, t[rise], side="right") - 1
    dio_at_rise = dio[dio_idx]
    bits = "".join(str(int(x)) for x in dio_at_rise)

    # half-period stats on clk
    dt = np.diff(t[rise])
    print("clk period (rising->rising) ns: median=%.1f p10=%.1f p90=%.1f min=%.1f max=%.1f"
          % (np.median(dt), np.percentile(dt, 10), np.percentile(dt, 90), dt.min(), dt.max()))
    print("SWCLK = %.2f MHz" % (1000.0 / np.median(dt)))

    # frames separated by clock gaps
    gap_idx = np.where(dt > args.gap_ns)[0]
    starts = np.concatenate(([0], gap_idx + 1))
    ends = np.concatenate((gap_idx, [len(rise) - 1]))
    frames = []
    for s, e in zip(starts, ends):
        frames.append((t[rise[s]], t[rise[e]], e - s + 1))
    print(f"frames={len(frames)}")
    lens = [f[2] for f in frames]
    print("clocks/frame: median=%d p10=%d p90=%d min=%d max=%d"
          % (int(np.median(lens)), int(np.percentile(lens, 10)), int(np.percentile(lens, 90)), min(lens), max(lens)))
    durs = [f[1] - f[0] for f in frames]
    print("frame duration ns: median=%.1f" % np.median(durs))

    # gaps between frames
    gaps = [frames[i + 1][0] - frames[i][1] for i in range(len(frames) - 1)]
    if gaps:
        print("inter-frame gap ns: median=%.1f p10=%.1f p90=%.1f max=%.1f"
              % (np.median(gaps), np.percentile(gaps, 10), np.percentile(gaps, 90), max(gaps)))
        hist = Counter(int(g // 100) * 100 for g in gaps)
        print("gap histogram (100ns bins, top):", hist.most_common(10))

    # bursts separated by large gaps
    if gaps:
        bg = np.array(gaps)
        burst_idx = np.where(bg > args.burst_ns)[0]
        bstarts = np.concatenate(([0], burst_idx + 1))
        bends = np.concatenate((burst_idx, [len(frames) - 1]))
        print(f"bursts={len(bstarts)}")
        for k, (s, e) in enumerate(zip(bstarts, bends)):
            if k < 20:
                print(f"  burst {k}: frames={e - s + 1} dur={frames[e][1] - frames[s][0]:.0f} ns")
        if len(bstarts) > 1:
            bgaps = [frames[bstarts[i + 1]][0] - frames[bends[i]][1] for i in range(len(bstarts) - 1)]
            print("burst gap ns: ", " ".join(f"{g:.0f}" for g in bgaps[:15]))

    # print the first bits for a sanity check
    print("first 96 sampled bits:", bits[:96])


if __name__ == "__main__":
    main()
