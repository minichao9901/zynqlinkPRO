"""Run the J200 ARM MEM-AP pipeline on backed-up H743 AXI SRAM."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import random
import subprocess
import sys
import time

import usb.util

from dap_pipeline_bench import open_dap, setup, xfer
from jtag200 import ROOT
from jtag200_h743_baseline import BASE, DHCSR, SIZE, SUPPLY, ClockFixture, sha
from jtag200_h743_scan import IDCODE, identify, select, slow_read
from jtag200_pipeline import BlockBenchmark, Ownership, PhysicalPort, need
from target_snapshot import same_clock_configuration, snapshot
from test_probe_board import Memory

BIT = 'prebuilt/release-20261106/probe.bit'
ELF = 'prebuilt/h743-jtag66-20261109/application.elf'
INIT = 'prebuilt/release-20261106/ps7_init.tcl'
SDK = Path('E:/Xilinx/SDK/2018.3')


@contextmanager
def low_link(serial):
    deadline = time.monotonic() + 10
    while True:
        try:
            device, out, data = open_dap(serial)
            break
        except RuntimeError as error:
            if str(error) != f'Expected one ZynqLinkPRO DAP with serial {serial}, found 0':
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)
    try:
        need(setup(out, data, 10000, 'jtag') == b'\x16\x00' + IDCODE.to_bytes(4, 'little'),
             'Unexpected ARM TAP, no target write')
        mem = Memory(out, data)
        need(snapshot(mem)['device'] == '0x20036450', 'Expected H743 rev. V')
        yield mem
    finally:
        try:
            xfer(out, data, [3])
        finally:
            usb.util.dispose_resources(device)


def guard_bytes(mem):
    return mem.read(BASE - 4, 4) + mem.read(BASE + SIZE, 4)


def historical_probe(path):
    subprocess.run([sys.executable, '-X', 'utf8', 'toolbox.py', 'probe-load',
                    '--bit', BIT, '--elf', ELF, '--ps-init', INIT, '--out', str(path)],
                   cwd=ROOT, check=True)


def trial(bench, rate, timing, idle, direction, seconds, *, profile=False,
          stream=False, verify_in_pl=False):
    tap, sample, advance = timing
    bench.configure(rate, idle, sample, advance_tms=advance, advance_tdi=advance, arm=True,
                    stream=stream, verify_in_pl=verify_in_pl)
    result = bench.run(direction, seconds, profile=profile)
    del result['dmi_busy'], result['dmi_invalid']
    result.pop('wire_dmi', None)
    return dict(rate=rate, tap=tap, sample=sample, advance=advance, idle=idle,
                stream=stream, verify_in_pl=verify_in_pl, **result)


def compare_66(bench, report, archive, seconds):
    rate = '66.667-block'
    timing = None
    for tap in (16, 0, 8, 24, 31):
        half, hz = select(bench.port, rate, tap)
        slots = sorted(identify(bench.port, half, 3))
        control = int(bench.port.command('read_word 0xf8000180'))
        io_pll = int(bench.port.command('read_word 0xf8000108'))
        need(control & 0x03F03F30 == 0x00103000 and io_pll >> 12 & 127 == 48,
             '66 MHz FCLK1/IO PLL registers did not match')
        report['calibration'].append(dict(rate=rate, tap=tap, slots=slots, nominal_tck_hz=hz,
                                          fclk_control=hex(control), io_pll_control=hex(io_pll)))
        for phase in sorted(slots, key=lambda phase: abs(phase - 34)):
            for advance in (True, False):
                candidate = (tap, phase, advance)
                row = trial(bench, rate, candidate, 3, 1, 1, profile=True)
                report['read_tune'].append(row)
                archive()
                if row['passed'] and (timing is None or row['read_MBps'] > timing[0]):
                    timing = row['read_MBps'], candidate
        if timing is not None:
            break
    need(timing is not None, 'No 66.667 MHz calibrated ARM block read')
    tap, phase, advance = timing[1]
    for idle, window in ((1, 1), (3, seconds), (5, seconds), (8, 1), (12, 1)):
        select(bench.port, rate, tap)  # Reset the cumulative wire counters for this window.
        row = trial(bench, rate, timing[1], idle, 1, window, profile=True)
        report['long_read'].append(row)
        print(json.dumps(row), flush=True)
        archive()
    pattern = random.Random(0x743666).randbytes(1024)
    bench.pattern(pattern)
    report['phase'] = 'write'
    archive()
    for idle in (5, 8, 12):
        select(bench.port, rate, tap)
        row = trial(bench, rate, (tap, phase, advance), idle, 0, 2, profile=True)
        report['mixed'].append(row)
        print(json.dumps(row), flush=True)
        archive()
        if row['passed']:
            select(bench.port, rate, tap)
            row = trial(bench, rate, (tap, phase, advance), idle, 0, seconds, profile=True)
            report['mixed'].append(row)
            print(json.dumps(row), flush=True)
            archive()
            if row['passed']:
                break


def compare_stream_66(bench, report, archive, seconds):
    rate = '66.667-block'
    timing = None

    def run(timing, idle, direction, window, stream, verify):
        select(bench.port, rate, timing[0])
        row = trial(bench, rate, timing, idle, direction, window, profile=True,
                    stream=stream, verify_in_pl=verify)
        print(json.dumps(row), flush=True)
        return row

    for tap in (16, 8, 24, 0, 31):
        half, hz = select(bench.port, rate, tap)
        slots = identify(bench.port, half, 3)
        control = int(bench.port.command('read_word 0xf8000180'))
        io_pll = int(bench.port.command('read_word 0xf8000108'))
        need(control & 0x03F03F30 == 0x00103000 and io_pll >> 12 & 127 == 48,
             '66 MHz FCLK1/IO PLL registers did not match')
        report['calibration'].append(dict(rate=rate, tap=tap, slots=sorted(slots), nominal_tck_hz=hz,
                                          fclk_control=hex(control), io_pll_control=hex(io_pll)))
        for idle in (3, 5, 9, 17):
            for phase in sorted(slots, key=lambda phase: abs(phase - 32)):
                candidate = (tap, phase, False)
                row = run(candidate, idle, 1, 1, True, False)
                report['read_tune'].append(row)
                archive()
                if row['passed']:
                    timing, read_idle = candidate, idle
                    break
            if timing:
                break
        if timing:
            break
    need(timing is not None, 'No streaming read at 66.667 MHz with independent A9 comparison')

    for idle, duration, stream, verify in ((3, 2, False, False), (read_idle, 2, True, False),
                                          (read_idle, seconds, True, True), (1, 2, True, True)):
        report['long_read'].append(run(timing, idle, 1, duration, stream, verify))
        archive()

    # Keep the 100 MHz follow-up read-only and use the same saved target data.
    report['stream100_read'] = []
    half, _ = select(bench.port, '100', 16)
    slots = identify(bench.port, half, 3)
    for idle in (3, 5, 9, 17, 33):
        for sample in sorted(slots, key=lambda phase: abs(phase - 37)):
            candidate = (16, sample, True)
            select(bench.port, '100', 16)
            probe = trial(bench, '100', candidate, idle, 1, 0, profile=True, stream=True)
            report['stream100_read'].append(probe)
            if probe['passed']:
                select(bench.port, '100', 16)
                row = trial(bench, '100', candidate, idle, 1, min(seconds, 10),
                            profile=True, stream=True, verify_in_pl=True)
                report['stream100_read'].append(row)
                print(json.dumps(row), flush=True)
                if row['passed']:
                    break
        else:
            continue
        break
    archive()

    pattern = random.Random(0x743666).randbytes(1024)
    bench.pattern(pattern)
    report['phase'] = 'write'
    archive()
    for stream in (False, True):
        result = run(timing, 5, 0, 2, stream, False)
        report['mixed'].append(result)
        archive()
    for idle in sorted({5, 7, 9, 13, max(5, read_idle)}):
        pilot = run(timing, idle, 0, 1, True, True)
        report['mixed'].append(pilot)
        archive()
        if pilot['passed']:
            result = run(timing, idle, 0, seconds, True, True)
            report['mixed'].append(result)
            archive()
            if result['passed']:
                break
    need(any(row['passed'] and row['verify_in_pl'] and row['planned_s'] == seconds
             for row in report['long_read']), 'Sustained SRAM read failed')
    need(report['mixed'][-1]['passed'] and report['mixed'][-1]['planned_s'] == seconds,
         'Sustained alternating SRAM verification failed')




def sweep(bench, report, archive):
    results = {}
    for rate, taps, phases in (('50', (16,), (36, 38, 34)),
                               ('100', (16, 24, 8, 0, 31), (37, 36, 38, 39, 35)),
                               ('80', (16, 24), (35, 36, 34, 37)),
                               ('160', (24, 8, 0, 16, 31), (35, 36, 37, 38, 34)),
                               ('200', (16, 24, 8, 0, 31), (37, 38, 39, 40, 36))):
        advance = rate in ('80', '100')
        selected = None
        for tap in taps:
            half, hz = select(bench.port, rate, tap)
            slots = sorted(identify(bench.port, half, 3))
            report['calibration'].append(dict(rate=rate, tap=tap, nominal_tck_hz=hz, slots=slots,
                                              fclk_control=bench.port.command('read_word 0xf8000180')))
            # 50 MHz identified this target. At the higher rates a missing
            # raw ID keeps the scan read-only and ends this tap attempt.
            if not slots:
                continue
            for phase in phases:
                timing = (tap, phase, advance)
                row = trial(bench, rate, timing, 96, 1, 0)
                report['read_tune'].append(row)
                if row['passed']:
                    row = trial(bench, rate, timing, 96, 1, 1)
                    report['read_tune'].append(row)
                    if row['passed']:
                        selected = timing
                        break
            if selected is not None:
                break
        archive()
        if selected is None:
            print(f'{rate} MHz: no verified 1 KiB block', flush=True)
            continue
        results[rate] = []
        for idle in (96, 64, 40, 32, 24, 20, 16, 12, 8, 6, 5, 4, 3, 2, 1):
            row = trial(bench, rate, selected, idle, 1, 1)
            report['read_tune'].append(row)
            if row['passed']:
                results[rate].append((row['read_MBps'], selected, idle))
        print(f'{rate} MHz: best 1 second reads {sorted(results[rate], reverse=True)[:3]}', flush=True)
        archive()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--cable-serial', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--seconds', default=60, type=int, choices=range(1, 61), metavar='1..60')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--compare-66', action='store_true', help='Profile only the 66.667 MHz ARM path')
    mode.add_argument('--stream-66', action='store_true', help='Compare ARM stream and PL verification at 66.667 MHz')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print('Temporary H743 480/240 MHz, guarded 1 KiB blocks; restore 4 KiB AXI SRAM at 10 MHz.')
        return

    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(calibration=[], read_tune=[], long_read=[], mixed=[], phase='preflight')

    def archive():
        (args.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')

    fixture = saved = guards = initial = None
    historical_probe(args.out / 'prepare-probe')
    try:
        with low_link(args.serial) as mem:
            report['target_before'] = snapshot(mem)
            need(mem.word(0xE000ED14) & (1 << 16) == 0, 'D-cache enabled')
            fixture = ClockFixture(mem)
            initial = mem.word(DHCSR)
            mem.write_word(DHCSR, 0xA05F0003)
            fixture.wait(DHCSR, 1 << 17, 1 << 17)
            saved = mem.read(BASE, SIZE)
            guards = guard_bytes(mem)
            need(saved == mem.read(BASE, SIZE) and guards == guard_bytes(mem), 'backup differs')
            (args.out / 'backup.bin').write_bytes(saved)
            (args.out / 'guards.bin').write_bytes(guards)
            report['backup_sha256'] = sha(saved)
            report['dhcsr_before'] = hex(initial)
            archive()
            fixture.enable(report, archive)
        subprocess.run([sys.executable, '-X', 'utf8', 'tools/jtag200.py', 'load',
                        '--pair', str(args.pair.resolve()), '--sdk', str(SDK), '--execute',
                        '--cable-serial', args.cable_serial, '--out', str(args.out / 'fast-probe')],
                       cwd=ROOT, check=True)
        lock = Ownership()
        try:
            port = PhysicalPort(args.out, args.cable_serial, SDK)
            try:
                report['probe'] = port.verify_probe(args.pair)
                half, _ = select(port, '50', 16)
                calibrated = identify(port, half, 3)
                need(calibrated, '50 MHz ARM ID qualification failed')
                for address in (0x5C001000, 0x58024400, 0x58024410, 0x58024418, 0x58024428, 0x58024430):
                    key = hex(address)
                    expected = 0x20036450 if address == 0x5C001000 else int(
                        report['target_clock_active']['registers'][key], 16)
                    observed = slow_read(port, half, 0, address, 1, calibrated)
                    mask = 0xFFFF3FFF if address == 0x58024400 else 0xFFFFFFFF
                    calibrated = {phase for phase in calibrated
                                  if all(ack == 2 for ack in observed[phase]['acks'])
                                  and observed[phase]['status'] & 0xA2 == 0
                                  and (observed[phase]['values'][0] >> 3) & mask == expected & mask}
                    need(calibrated, f'Clock/identity changed at {key}')
                report['target_clock_reverified'] = True
                report['target_clock_probe_slots'] = sorted(calibrated)
                report['phase'] = 'read'
                bench = BlockBenchmark(port, args.out)
                bench.pattern(saved[:1024])
                if args.stream_66:
                    compare_stream_66(bench, report, archive, args.seconds)
                elif args.compare_66:
                    compare_66(bench, report, archive, args.seconds)
                else:
                    results = sweep(bench, report, archive)
                    for rate in ('100', '200', '160', '80', '50'):
                        for _, timing, idle in sorted(results.get(rate, []), reverse=True)[:3]:
                            select(port, rate, timing[0])
                            seconds = min(args.seconds, 10) if rate in ('50', '80') else args.seconds
                            row = trial(bench, rate, timing, idle, 1, seconds)
                            report['long_read'].append(row)
                            archive()
                            print(json.dumps(row), flush=True)
                            if row['passed']:
                                break
                    eligible = [r for r in report['long_read'] if r['passed']]
                    chosen_by_rate = {r['rate']: r for r in eligible}
                    write_rates = ('100', '200', '160') if '100' in chosen_by_rate else ('200', '160', '80')
                    for write_rate in write_rates:
                        if write_rate not in chosen_by_rate:
                            continue
                        chosen = chosen_by_rate[write_rate]
                        rate = chosen['rate']
                        timing = (chosen['tap'], chosen['sample'], chosen['advance'])
                        select(port, rate, timing[0])
                        pattern = random.Random(0x743100).randbytes(1024)
                        bench.pattern(pattern)
                        report['phase'] = 'write'
                        archive()
                        for idle in dict.fromkeys((chosen['idle'], 24, 40, 96)):
                            row = trial(bench, rate, timing, idle, 0, 2)
                            report['mixed'].append(row)
                            archive()
                            print(json.dumps(row), flush=True)
                            if row['passed']:
                                row = trial(bench, rate, timing, idle, 0, args.seconds)
                                report['mixed'].append(row)
                                archive()
                                print(json.dumps(row), flush=True)
                                if row['passed']:
                                    break
                report['phase'] = 'complete'
            finally:
                port.close()
        finally:
            lock.close()
    except Exception as exc:
        report['error'] = repr(exc)
        raise
    finally:
        try:
            historical_probe(args.out / 'restore-probe')
            with low_link(args.serial) as mem:
                if saved is not None:
                    before_restore = mem.read(BASE, SIZE)
                    if args.stream_66 and report['mixed'] and report['mixed'][-1]['passed']:
                        last = report['mixed'][-1]
                        pattern = random.Random(0x743666).randbytes(1024)
                        if (last['write_bytes'] // 1024 - 1) & 1:
                            pattern = bytes(value ^ 255 for value in pattern)
                        report['independent_final_pattern_match'] = before_restore == pattern + saved[1024:]
                    if before_restore != saved:
                        mem.write(BASE, saved)
                    restored = mem.read(BASE, SIZE)
                    report['restore_sha256'] = sha(restored)
                    report['ram_restored'] = restored == saved
                    report['guards_match'] = guard_bytes(mem) == guards
                if fixture is not None:
                    fixture.mem = mem
                    try:
                        report['voltage_restored'] = fixture.restore()
                        report['supply_after'] = hex(mem.word(SUPPLY))
                        report['target_after'] = snapshot(mem)
                        report['rcc_restored'] = same_clock_configuration(
                            report['target_before'], report['target_after'])
                    finally:
                        if initial is not None:
                            mem.write_word(DHCSR, 0xA05F0000 | (initial & 0x2F))
                            report['dhcsr_after'] = hex(mem.word(DHCSR))
                            report['core_state_restored'] = (int(report['dhcsr_after'], 16) ^ initial) & 0x2002F == 0
        except Exception as exc:
            report['restore_error'] = repr(exc)
            raise
        finally:
            archive()
    need(all(report.get(key) for key in ('ram_restored', 'guards_match', 'voltage_restored',
                                        'rcc_restored', 'core_state_restored')), 'Restore verification failed')
    if args.stream_66:
        need(report.get('independent_final_pattern_match'), 'Independent final data check failed')


if __name__ == '__main__':
    main()
