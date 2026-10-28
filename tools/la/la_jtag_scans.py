"""Capture TCK/TMS and count DR scans, to verify WAIT retries on hardware.

CH0 = TCK, CH1 = TMS. One DR scan is a burst of TCK pulses; consecutive scans
are separated by an FSM/packet gap that is orders of magnitude longer than a
TCK period, so bursts are trivially separable.
"""
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, r"E:\zynqlinkPRO\tools\la")
from kingst_la import Vis  # noqa: E402


def capture(rate, seconds, threshold, out, trigger=None):
    v = Vis()
    try:
        v.cmd("set-sample-rate %d" % rate)
        v.cmd("set-sample-time %f" % seconds)
        v.cmd("set-threshold-voltage %f" % threshold)
        if trigger:
            v.cmd("set-trigger " + trigger)
        else:
            v.cmd("set-trigger --reset")
        t0 = time.time()
        v.cmd("start", timeout=120)
        depth = v.cmd("get-actual-sample-depth")
        span = v.cmd("get-actual-sample-time")
        print("captured depth=%s span=%s in %.2fs" % (depth, span, time.time() - t0))
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        v.cmd('export-data "%s"' % out.as_posix(), timeout=600)
        deadline = time.time() + 120
        while time.time() < deadline and (not out.exists() or out.stat().st_size == 0):
            time.sleep(0.1)
        print("export %s size=%s" % (out, out.stat().st_size if out.exists() else "missing"))
    finally:
        v.close()


def analyse(path, gap_ns):
    rises = []
    duration = 0.0
    first = None
    last = None
    prev = None
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            if len(row) < 3:
                continue
            t = float(row[0])
            tck = int(row[1])
            tms = int(row[2])
            if first is None:
                first = t
            last = t
            if prev is not None and prev[0] == 0 and tck == 1:
                rises.append((t, tms))
            prev = (tck, tms)
    duration = (last - first) if (first is not None and last is not None) else 0.0

    bursts = []
    if rises:
        start = rises[0][0]
        count = 1
        prev_t = rises[0][0]
        for t, _ in rises[1:]:
            if (t - prev_t) * 1e9 > gap_ns:
                bursts.append((start, prev_t, count))
                start = t
                count = 1
            else:
                count += 1
            prev_t = t
        bursts.append((start, prev_t, count))

    periods = sorted((b - a) * 1e9 for a, b in zip([x[0] for x in rises], [x[0] for x in rises[1:]])
                     if (b - a) * 1e9 <= gap_ns)
    print("window %.3f ms, TCK rising edges %d" % (duration * 1e3, len(rises)))
    if duration:
        print("  edge rate %.2f M/s" % (len(rises) / duration / 1e6))
        print("  bursts(scans) %d -> %.0f scans/s" % (len(bursts), len(bursts) / duration))
    if periods:
        periods.sort()
        print("  intra-scan TCK period: median %.1f ns (=> %.2f MHz)"
              % (periods[len(periods) // 2], 1e3 / periods[len(periods) // 2]))
    if bursts:
        sizes = sorted(b[2] for b in bursts)
        print("  pulses per scan: median %d, min %d, max %d"
              % (sizes[len(sizes) // 2], sizes[0], sizes[-1]))
        gaps = sorted((b[0] - a[1]) * 1e9 for a, b in zip(bursts, bursts[1:]))
        if gaps:
            print("  inter-scan gap: median %.0f ns, p10 %.0f, p90 %.0f"
                  % (gaps[len(gaps) // 2], gaps[len(gaps) // 10], gaps[len(gaps) * 9 // 10]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rate', type=int, default=500000000)
    ap.add_argument('--time', type=float, default=0.01)
    ap.add_argument('--threshold', type=float, default=1.65)
    ap.add_argument('--gap-ns', type=float, default=200.0)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--analyse-only', action='store_true')
    a = ap.parse_args()
    a.out = a.out.resolve()
    if not a.analyse_only:
        capture(a.rate, a.time, a.threshold, a.out)
    analyse(a.out, a.gap_ns)


if __name__ == '__main__':
    main()
