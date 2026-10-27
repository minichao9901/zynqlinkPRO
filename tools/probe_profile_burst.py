"""Run a block-read burst with the firmware's per-phase profiling enabled.

Leaves dap_metrics populated in RAM; read them with
tools/read_probe_counters.tcl to split PL engine time from USB/PS time.
"""
import argparse
from pathlib import Path

from dap_pipeline_bench import open_dap, setup, cmd, block_read_req, send, read_exact


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--transport', default='jtag')
    ap.add_argument('--speed', type=int, default=60000)
    ap.add_argument('--words', type=int, default=256)
    ap.add_argument('--loops', type=int, default=64)
    ap.add_argument('--depth', type=int, default=8)
    a = ap.parse_args()

    dev, out, inp = open_dap()
    setup(out, inp, a.speed, a.transport)
    cmd(out, inp, [0x81, 1])                      # start profiling
    done = 0
    while done < a.loops:
        n = min(a.depth, a.loops - done)
        for _ in range(n):
            send(out, block_read_req(a.words))
        for _ in range(n):
            read_exact(inp, 4 + a.words * 4)
        done += n
    cmd(out, inp, [0x81, 0])                      # stop profiling
    print('%s %d kHz: %d words profiled' % (a.transport, a.speed,
                                            a.loops * a.words))


if __name__ == '__main__':
    main()
