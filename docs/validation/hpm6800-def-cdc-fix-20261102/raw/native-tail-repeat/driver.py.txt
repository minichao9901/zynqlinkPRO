"""HPM6800EVK RAM-only acceptance; load/verify the probe pair separately.

Never resets the target or writes Flash/PLL. SRAM windows are backed up while
hart0 is halted and restored byte-for-byte before its original state is resumed.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import random
import statistics
import struct
import time

import usb.util

from benchmark_hpm5301 import setup, clock
from dap_pipeline_bench import open_dap, drain, send, read_exact, xfer, le
from probe_build_info import provenance
from probe_stream import Probe
from riscv_target import RiscvTarget
from test_probe_board import Memory
from validate_fclk_performance import physical_snapshot


def driver_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = ['tools/validate_hpm6800_performance.py', 'tools/validate_hpm6800_streams.py',
             'tools/benchmark_hpm5301.py', 'tools/riscv_target.py', 'tools/test_probe_board.py',
             'tools/dap_pipeline_bench.py', 'tools/probe_build_info.py', 'firmware/target/hpm6800_perf_ram.S']
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths}


class SramMemory(Memory):
    # SBA increments linearly, unlike ARM MEM-AP TAR. Packet capacity remains
    # bounded by the existing Memory helper; explicit addresses bound windows.
    TAR_WRAP = 0x100000000


def target_clocks(target):
    """Only previously qualified HPM6880 clock controls, no gated/reserved PLL reads."""
    controls = {name: target.word(at) for name, at in
                [('cpu0', 0xf4001800), ('mchtmr0', 0xf4001804), ('ahb', 0xf4001810)]}
    return dict(controls={k: hex(v) for k, v in controls.items()},
                basis='Read-only qualified SYSCTL controls; target frequencies not inferred without qualified PLL outputs')


def recover_link(dev, out, inp):
    from test_swd_lowfreq_board import recover
    recover(dev, inp)
    xfer(out, inp, [0x11] + le(10_000_000))
    target = RiscvTarget(out, inp)
    target.select(16)
    target.scan(1 << 16, 32)
    target = RiscvTarget(out, inp)
    target.active()
    sbcs = target.dmi(0x38)
    if sbcs & (1 << 21):
        raise RuntimeError(f'SBA still busy: {sbcs:#x}; no reset or busy config write')
    target.dmi(0x38, 0x447000)
    setup(out, inp, 10_000_000, 0)


def peak(mem, base, size, pattern, loops, repeats):
    words, depth = 512, min(32, size // 2048)
    result = dict(words=words, depth=depth, loops=loops, window_bytes=size)
    for direction in ('read', 'write'):
        rates, times, scan_stats = [], [], []
        for repeat in range(repeats + 1):
            before = struct.unpack_from('<3I', xfer(mem.out, mem.inp, [0x89, 255]), 3)
            started = time.perf_counter()
            for done in range(0, loops, depth):
                count = min(depth, loops - done)
                mem.address(base)
                for i in range(count):
                    packet = bytes([6, 0, 0, 2, 15 if direction == 'read' else 13])
                    if direction == 'write':
                        packet += pattern[i * 2048:(i + 1) * 2048]
                    send(mem.out, packet)
                for i in range(count):
                    reply = read_exact(mem.inp, 2052 if direction == 'read' else 4)
                    assert reply[:4] == bytes([6, 0, 2, 1]), reply[:32].hex()
                    if direction == 'read':
                        assert reply[4:] == pattern[i * 2048:(i + 1) * 2048], 'SRAM byte mismatch'
            elapsed = time.perf_counter() - started
            after = struct.unpack_from('<3I', xfer(mem.out, mem.inp, [0x89, 255]), 3)
            if repeat:
                times.append(elapsed)
                rates.append(loops * 2048 / elapsed / 1e6)
                delta = [(b - a) & 0xffffffff for a, b in zip(before, after)]
                scan_stats.append(dict(phy_wait_fclk_cycles=delta[0], shifted_bits=delta[1], scans=delta[2],
                                       scans_per_word=delta[2] / (loops * words), bits_per_word=delta[1] / (loops * words)))
        result[direction + '_MB_s'] = statistics.median(rates)
        result[direction + '_repeats_MB_s'] = rates
        result[direction + '_seconds'] = times
        result[direction + '_scan_stats'] = scan_stats
    assert mem.read(base, size) == pattern, 'Write readback mismatch'
    result['all_bytes_verified'] = True
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bit', type=Path, required=True)
    p.add_argument('--elf', type=Path, required=True, help='Probe PS ELF')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--speeds', default='1000000,10000000,15000000,20000000,25000000,35000000,50000000,60000000')
    p.add_argument('--windows', default='axi,ahb')
    p.add_argument('--loops', type=int, default=128)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--sustain-seconds', type=float, default=0, help='Additional alternating full-window byte-checked stress per accepted point')
    p.add_argument('--skip-high-idcode', action='store_true', help='Diagnostic: identify/activate at 10MHz, then test DMI at requested TCK')
    p.add_argument('--idle', type=int, choices=range(65), help='Explicit idle; >15 requires the extended-idle pair')
    p.add_argument('--modes', default='0,1,17,16', help='Explicit capture profile order')
    a = p.parse_args()
    if a.loops <= 0 or a.repeats <= 0 or a.sustain_seconds < 0:
        p.error('--loops/--repeats must be positive and --sustain-seconds nonnegative')
    modes = list(map(int, a.modes.split(',')))
    if not modes or any(v not in (0, 1, 16, 17) for v in modes):
        p.error('Invalid capture modes')
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
    report = dict(time=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  artifacts=provenance(a.bit, a.elf), rows=[], target='HPM6800EVK / hart0',
                  target_flash_writes=False, target_resets=False, target_clock_writes=False)
    report['driver_sha256'] = driver_hashes()
    def save():
        (a.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    report['probe_before'] = physical_snapshot()
    save()
    assert report['probe_before']['allObservedEnginesIdle'], report['probe_before']
    dev, out, inp = open_dap()
    probe = Probe()
    mem = SramMemory(out, inp)
    initial = None
    backups = {}
    try:
        for service in (0x31, 0x32):
            rc, info = probe.action(service, 2)
            report[f'service_{service:x}_before'] = [rc, info]
            assert not info[0] & 1, ('Service already active', service, rc, info)
        drain(inp)
        setup(out, inp, 10_000_000, 0, connect=True)
        target = RiscvTarget(out, inp)
        target.active()
        initial = target.dmi(0x11)
        report['initial_dmstatus'] = hex(initial)
        target.halt()
        report['dpc'] = hex(target.register(0x7b1))
        report['target_clocks_before'] = target_clocks(target)
        report['target_clock_registers_before'] = [hex(target.word(x)) for x in (0xf4001800, 0xf4001804)]
        setup(out, inp, 10_000_000)
        windows = {'axi': (0x01240000, 65536), 'ahb': (0xf0400000, 32768), 'axi-last': (0x0127f000, 4096)}
        for name in a.windows.split(','):
            base, size = windows[name]
            backup = mem.read(base, size)
            assert mem.read(base, size) == backup, 'Backup read not repeatable'
            backups[name] = (base, backup)
            (a.out / f'{name}-backup.bin').write_bytes(backup)
            report.setdefault('backups', {})[name] = dict(base=hex(base), size=size, sha256=hashlib.sha256(backup).hexdigest())
            save()
            for speed in map(int, a.speeds.split(',')):
                row = dict(window=name, base=hex(base), requested_Hz=speed, passed=False, attempts=[])
                for mode in modes:
                    attempt = dict(mode=mode)
                    try:
                        if a.idle is not None:
                            setup(out, inp, 10_000_000, 0)
                            assert mem.transfer([4, a.idle, 64, 0, 0, 0]) == b'\x04\x00'
                            query = mem.transfer([0x8d, 255])
                            assert len(query) == 4 and query[:2] == b'\x8d\x00' and query[2] == max(8, a.idle), ('Idle not applied', query.hex())
                            attempt['effective_dmi_idle'] = query[2]
                            setup(out, inp, 10_000_000, 0)
                        if a.skip_high_idcode:
                            setup(out, inp, 10_000_000, 0)
                            assert xfer(out, inp, [0x11] + le(speed)) == b'\x11\x00'
                            assert xfer(out, inp, [0x89, mode])[:3] == bytes([0x89, 0, mode])
                            attempt['idcode_verified_at_Hz'] = 10_000_000
                        else:
                            setup(out, inp, speed, mode)
                        attempt.update(clock(out, inp))
                        data = random.Random(speed + mode).randbytes(4096)
                        mem.write(base, data)
                        assert mem.read(base, 4096) == data, 'Random SRAM mismatch'
                        assert mem.read(base + 3, 4093) == data[3:], 'Unaligned read mismatch'
                        attempt['functional_passed'] = True
                        pattern = random.Random(0x6800).randbytes(size)
                        mem.write(base, pattern)
                        measured = peak(mem, base, size, pattern, a.loops, a.repeats)
                        if a.sustain_seconds:
                            started = time.perf_counter()
                            rounds = 0
                            patterns = (pattern, bytes(x ^ 255 for x in pattern))
                            while time.perf_counter() - started < a.sustain_seconds:
                                data = patterns[rounds & 1]
                                mem.write(base, data)
                                assert mem.read(base, size) == data, 'Sustained byte mismatch'
                                rounds += 1
                            measured['sustained'] = dict(seconds=time.perf_counter()-started, rounds=rounds,
                                                        bytes_each_direction=rounds*size, all_bytes_verified=True)
                        row.update(passed=True, accepted_mode=mode, **clock(out, inp), **measured)
                    except Exception as exc:
                        attempt['error'] = repr(exc)
                        attempt['failure_clock'] = clock(out, inp)
                    finally:
                        row['attempts'].append(attempt)
                        report['active_row'] = row
                        save()
                        recover_link(dev, out, inp)
                        mem.write(base, backup)
                        attempt['restore_match'] = mem.read(base, size) == backup
                        assert attempt['restore_match'], 'SRAM restore mismatch'
                    if row['passed']:
                        break
                report['rows'].append(row)
                report.pop('active_row', None)
                save()
                print(json.dumps(row), flush=True)
        report['throughput_goal_passed'] = any(r['passed'] and min(r['read_MB_s'], r['write_MB_s']) > 1.5 for r in report['rows'])
    except BaseException as exc:
        report['failure'] = repr(exc)
        raise
    finally:
        try:
            recover_link(dev, out, inp)
            for name, (base, data) in backups.items():
                mem.write(base, data)
                report.setdefault('restore', {})[name] = mem.read(base, len(data)) == data
                assert report['restore'][name], 'Final SRAM restore mismatch'
            if initial is not None:
                target = RiscvTarget(out, inp)
                target.active()
                report['target_clocks_after'] = target_clocks(target)
                assert report['target_clocks_after'] == report['target_clocks_before'], 'Target PLL/clock configuration changed'
                report['target_clock_registers_after'] = [hex(target.word(x)) for x in (0xf4001800, 0xf4001804)]
                assert report['target_clock_registers_after'] == report['target_clock_registers_before']
                assert hex(target.register(0x7b1)) == report['dpc'], 'Halted PC changed'
                if initial & (1 << 10):
                    target.resume()
                report['final_dmstatus'] = hex(target.dmi(0x11))
                assert bool(initial & (1 << 10)) == bool(int(report['final_dmstatus'], 16) & (1 << 10))
        except BaseException as exc:
            report['restore_error'] = repr(exc)
            raise
        finally:
            save()
            probe.close()
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)
    if any(not r['passed'] for r in report['rows']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
