"""Continuously byte-verify bounded SRAM bursts on the HPM5301 PL backend."""
import argparse
import json
from pathlib import Path
import random
import statistics
import time

import usb.util

from benchmark_hpm5301 import BASE, SIZE, STATE, clock, peak, recover_link, setup
from dap_pipeline_bench import open_dap
from probe_build_info import provenance
from probe_stream import Probe
from riscv_target import RiscvTarget
from test_probe_board import Memory, stop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--speed', type=int, default=24500000)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(artifacts=provenance(args.bit, args.elf), rows=[], errors=0)
    def save():
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    dev, out, inp = open_dap()
    probe = Probe()
    mem = Memory(out, inp)
    backup = None
    try:
        stop(probe, dev)
        setup(out, inp, 10000000, 0, connect=True)
        RiscvTarget(out, inp).resume()
        setup(out, inp, args.speed)
        report.update(clock(out, inp))
        report['target_cpu_Hz'] = mem.word(STATE + 4)
        report['measured_cpu_Hz_before'] = mem.word(STATE + 20)
        assert 355000000 < report['measured_cpu_Hz_before'] < 365000000
        heartbeat = mem.word(STATE + 16)
        backup = mem.read(BASE, SIZE)
        args.output.with_suffix('.backup.bin').write_bytes(backup)
        pattern = random.Random(0x53010).randbytes(SIZE)
        mem.write(BASE, pattern)
        assert mem.read(BASE, SIZE) == pattern
        start = time.perf_counter()
        while time.perf_counter() - start < args.seconds:
            row = peak(mem, out, inp, pattern, loops=32, repeats=1)
            report['rows'].append(row)
            save()
        report.update(elapsed_s=time.perf_counter() - start,
                      all_read_bytes_verified=True, all_writes_readback_verified=True,
                      heartbeat_before=heartbeat, heartbeat_after=mem.word(STATE + 16),
                      measured_cpu_Hz_after=mem.word(STATE + 20))
        assert report['heartbeat_after'] != heartbeat
        for direction in ('read', 'write'):
            values = [r[direction + '_MB_s'] for r in report['rows']]
            report[direction] = dict(median_MB_s=statistics.median(values), min_MB_s=min(values), max_MB_s=max(values))
        print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2), flush=True)
    except BaseException as exc:
        report['failure'] = repr(exc)
        report['errors'] += 1
        raise
    finally:
        try:
            recover_link(dev, out, inp)
            if backup is not None:
                mem.write(BASE, backup)
                report['restore_match'] = mem.read(BASE, SIZE) == backup
                assert report['restore_match']
        finally:
            save()
            probe.close()
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
