"""F103 RAM-only, identity-checked Golden/release/fixed133 performance study.

Never programs target Flash/QSPI or changes target RCC. Outputs must be new.
Use separate invocations for each phase; never run hardware phases concurrently.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import usb.util
from dap_pipeline_bench import open_dap, setup
from test_probe_board import Memory, stop
from test_swd_lowfreq_board import recover
from probe_stream import Probe
from probe_build_info import live_clock_snapshot
from jtag_internal_trace import run as xsct

ROOT = Path(__file__).resolve().parents[1]
PAIRS = {'fixed': 'fclk133-swd-fixed-test-20261101',
         'release': 'fclk133-release-20261101', 'golden': 'golden'}
EXPECTED = {
    'fixed': ('ef9252c87529078c1d18ea1c05c3a19a333a20e1eee16205646b88518899ebe7',
              'b7ffe71c0edc5b8ccbd04adb14a0e43fdb7e67082d1ee00655066ee2ddd0853f'),
    'release': ('af1031d3caa0d7bd3b6adffa911d26efdab9e0bfb5223fb18f70dabb70ebeeed',
                '2137f7d0f507c08574f36223130103c0710645cbfdefb5c1d8c8efb0cfb990a0'),
    'golden': ('1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473',
               'e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c'),
}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def command(out, label, argv, *, allowed_failure=False):
    print('START', label, flush=True)
    script = ROOT / argv[0]
    metadata = dict(argv=list(map(str, argv)), allowed_failure=allowed_failure,
                    startedAtUtc=datetime.now(timezone.utc).isoformat())
    if script.is_file():
        metadata['scriptSha256'] = hashlib.sha256(script.read_bytes()).hexdigest()
    save(out / (label + '-command.json'), metadata)
    with (out / (label + '.txt')).open('w', encoding='utf-8') as log:
        p = subprocess.run([sys.executable, *map(str, argv)], cwd=ROOT,
                           stdout=log, stderr=subprocess.STDOUT)
    metadata['returncode'] = p.returncode
    save(out / (label + '-command.json'), metadata)
    print('END', label, p.returncode, flush=True)
    if p.returncode and not allowed_failure:
        raise RuntimeError(label + ' failed; inspect its log')
    return p.returncode


def physical_snapshot():
    addresses = {'FCLK0_CTRL': 0xf8000170, 'FCLK1_CTRL': 0xf8000180,
                 'ARM_PLL': 0xf8000100, 'DDR_PLL': 0xf8000104, 'IO_PLL': 0xf8000108,
                 'CPU_CTRL': 0xf8000120, 'DDR_CTRL': 0xf8000124,
                 'USB0_CTRL': 0xf8000130, 'USB1_CTRL': 0xf8000134,
                 'FEATURES': 0x40030048, 'CAPTURE': 0x40030008,
                 'SWD_STATUS': 0x40010004, 'PACKET_STATUS': 0x42020004,
                 'DDR_STATUS': 0x40040008, 'CDMA_STATUS': 0x40020004}
    body = 'targets -set -filter {name =~ "APU"}\n'
    for name, address in addresses.items():
        body += f'puts [format "SNAP {name} %08X" [mrd -address-space AP0 -force -value {address:#x}]]\n'
    log = xsct(body)
    values = {k: int(v, 16) for k, v in re.findall(r'SNAP (\w+) ([0-9A-Fa-f]{8})', log)}
    assert len(values) == len(addresses), log
    idle = not (values['SWD_STATUS'] & 1 or values['PACKET_STATUS'] & 15
                or values['DDR_STATUS'] & 33 or values['CAPTURE'] & 1)
    idle = idle and bool(values['CDMA_STATUS'] & 2)
    return dict(recordedAtUtc=datetime.now(timezone.utc).isoformat(),
                registers={k: hex(v) for k, v in values.items()},
                allObservedEnginesIdle=idle, xsctOutput=log)


def target_snapshot():
    d, o, i = open_dap()
    try:
        setup(o, i, 1000)
        m = Memory(o, i)
        values = {k: hex(m.word(a)) for k, a in {
            'CPUID': 0xe000ed00, 'deviceId': 0xe0042000, 'DHCSR': 0xe000edf0,
            'DEMCR': 0xe000edfc, 'ETMCR': 0xe0041000, 'ETMSR': 0xe0041010,
            'ETMLSR': 0xe0041fb4, 'RCC_CR': 0x40021000, 'RCC_CFGR': 0x40021004}.items()}
        assert values['CPUID'] == '0x411fc231', values
        assert int(values['RCC_CFGR'], 16) == 5309450, values
        from elftools.elf.elffile import ELFFile
        segments = []
        with (ROOT / 'prebuilt/golden/f103ze-cdc48.elf').open('rb') as f:
            for s in ELFFile(f).iter_segments():
                if s['p_type'] == 'PT_LOAD' and s['p_filesz'] and 0x08000000 <= s['p_paddr'] < 0x08080000:
                    actual = m.read(s['p_paddr'], s['p_filesz'])
                    assert actual == s.data(), 'Target Flash differs from Golden CDC48 ELF'
                    segments.append(dict(address=s['p_paddr'], bytes=len(actual),
                                         sha256=hashlib.sha256(actual).hexdigest()))
        values['FlashSegments'] = segments
        values['targetHalted'] = bool(int(values['DHCSR'], 16) & (1 << 17))
        return values
    finally:
        usb.util.dispose_resources(d)


def etm_rtt(out, common, speed, transport, paused):
    label = f'{transport}-rtt-{speed}-etm-' + ('paused' if paused else 'original')
    report = dict(targetClockWrites=False, targetFlashWrites=False, paused=paused)
    d, o, i = open_dap()
    m = Memory(o, i)
    setup(o, i, 1000)
    before, lock = m.word(0xe0041000), m.word(0xe0041fb4)
    report.update(ETMCR_before=hex(before), ETMLSR_before=hex(lock))
    try:
        if paused:
            if lock & 3 == 3:
                m.write_word(0xe0041fb0, 0xc5acce55)
            m.write_word(0xe0041000, before | 0x400)
            for _ in range(100):
                if m.word(0xe0041010) & 2:
                    break
                time.sleep(.001)
            else:
                raise RuntimeError('ETM did not enter programming state')
        report['ETMCR_test'] = hex(m.word(0xe0041000))
        usb.util.dispose_resources(d)
        d = None
        report['returncode'] = command(out, label, [
            'tools/benchmark_rtt_forward.py', '--transport', transport,
            '--bootstrap-speed-khz', '1000', '--speeds', speed, '--chunks', '1024',
            '--seconds', '2', '--repeats', '3', '--output', out / (label + '.json'),
            *common], allowed_failure=True)
    finally:
        if d is None:
            d, o, i = open_dap()
            m = Memory(o, i)
            setup(o, i, 1000)
        try:
            if paused:
                if lock & 3 == 3:
                    m.write_word(0xe0041fb0, 0xc5acce55)
                m.write_word(0xe0041000, before)
                if lock & 3 == 3:
                    m.write_word(0xe0041fb0, 0)
            report['ETMCR_after'] = hex(m.word(0xe0041000))
            report['ETM_restored'] = report['ETMCR_after'] == hex(before)
            assert report['ETM_restored']
        finally:
            usb.util.dispose_resources(d)
            save(out / (label + '-etm.json'), report)
    result = json.loads((out / (label + '.json')).read_text())
    # A functional failure is retained, but recovery failure stops the study.
    assert result.get('restore_match') and result.get('registers_match'), result
    assert result['RCC_after'] == result['RCC_before']
    for row in result.get('rows', []):
        assert abs(row['actual_link_Hz'] - speed) < 10, 'RTT rate silently changed'
    if result.get('failure'):
        # STOP/EP0 recovery/SET_CONFIGURATION were observed insufficient after
        # the high-speed RTT fault. Preserve it and reload this exact RAM pair
        # before another condition, without resetting the F103 target.
        pair = Path(common[1]).parent
        command(out, label + '-probe-reload', ['tools/run_xsct.py',
                'tools/download_dap_fpga.tcl', pair / 'application.elf',
                pair / 'probe.bit', pair / 'ps7_init.tcl'])
        command(out, label + '-reload-identity', ['tools/verify_probe_ocm_code.py',
                '--elf', pair / 'application.elf', '--out-dir', out / (label + '-reload-identity')])


def hss_frontier(out, common, speed, transport):
    from benchmark_probe_stream import hss_point
    label = f'{transport}-hss-{speed}'
    report = dict(requested_Hz=speed, transport=transport, rows=[],
                  bit=str(common[1]), elf=str(common[3]))
    d, o, i = open_dap()
    p, m = Probe(), Memory(o, i)
    backup = initial = None
    path = out / (label + '.json')
    try:
        stop(p, d)
        setup(o, i, 1000)
        initial = m.word(0xe000edf0)
        if not initial & (1 << 17):
            m.write_word(0xe000edf0, 0xa05f0003)
        backup = m.read(0x20004000, 4096)
        path.with_suffix('.backup.bin').write_bytes(backup)
        report['backup_sha256'] = hashlib.sha256(backup).hexdigest()
        report['RCC_before'] = [m.word(0x40021000), m.word(0x40021004)]
        assert p.action(0x31, 12, bytes([1 if transport == 'swd' else 2]))[0] == 0

        def point(period, stage, seconds=.5):
            setup(o, i, 1000, 'swd')
            row = hss_point(p, m, d, speed, period, 1, seconds, len(report['rows']), True,
                            lambda: setup(o, i, 1000, transport), True)
            assert abs(row['actual_link_Hz'] - speed) < 10, 'HSS rate silently changed'
            row['stage'] = stage
            report['rows'].append(row)
            save(path, report)
            print(label, stage, period, row['effective_Hz'], row['skipped'], flush=True)
            return row

        # Test the public minimum first; otherwise bracket and refine the frontier.
        v = point(24, 'minimum')
        good = 24
        if v['skipped']:
            bad, good = 24, 48
            while point(good, 'bracket')['skipped']:
                bad, good = good, good * 2
                assert good <= 3072, 'Unexpectedly low HSS throughput'
            while good - bad > 1:
                mid = (good + bad) // 2
                if point(mid, 'refine')['skipped']:
                    bad = mid
                else:
                    good = mid
        for attempt in range(5):
            verified = [point(good, 'verify_zero', 2) for _ in range(3)]
            if all(v['skipped'] == 0 for v in verified):
                break
            good += 1
        stable = all(v['skipped'] == 0 for v in verified)
        report.update(passed=stable, zero_period_ticks=good if stable else None,
                      highest_verified_zero_skip_Hz=24000000 / good if stable else None,
                      min_period_effective_Hz=report['rows'][0]['effective_Hz'],
                      zero_verification_runs=3 if stable else 0,
                      control_sequence_errors=sum(len(v['control_sequence_errors']) for v in report['rows']))
    except BaseException as exc:
        report['failure'] = repr(exc)
        if hasattr(exc, 'measurement'):
            report['failed_measurement'] = exc.measurement
    finally:
        try:
            try:
                stop(p, d)
            except RuntimeError:
                recover(d, i)
                stop(p, d)
            setup(o, i, 1000)
            if backup is not None:
                m.write(0x20004000, backup)
                report['restore_match'] = m.read(0x20004000, 4096) == backup
                assert report['restore_match']
            report['RCC_after'] = [m.word(0x40021000), m.word(0x40021004)]
            assert report['RCC_before'] == report['RCC_after']
            if initial is not None and not initial & (1 << 17):
                m.write_word(0xe000edf0, 0xa05f0001)
        finally:
            save(path, report)
            p.close()
            usb.util.dispose_resources(d)
    assert report.get('passed'), report


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--pair', choices=list(PAIRS), required=True)
    a.add_argument('--out', type=Path, required=True)
    a.add_argument('--phase', choices=['inspect', 'load', 'swd', 'jtag', 'jtag-child'], required=True)
    args = a.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    marker = out / ('phase-' + args.phase + '.json')
    assert not marker.exists(), 'Do not overwrite prior evidence'
    pair = ROOT / 'prebuilt' / PAIRS[args.pair]
    files = {n: hashlib.sha256((pair / n).read_bytes()).hexdigest()
             for n in ['probe.bit', 'application.elf', 'ps7_init.tcl']}
    assert (files['probe.bit'], files['application.elf']) == EXPECTED[args.pair]
    common = ['--bit', pair / 'probe.bit', '--elf', pair / 'application.elf']
    report = dict(startedAtUtc=datetime.now(timezone.utc).isoformat(), pair=str(pair), files=files,
                  phase=args.phase, targetFlashWrites=False, QSPIWrites=False, targetClockWrites=False)
    report['driverSha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save(marker, report)
    try:
        if args.phase in ['inspect', 'load']:
            snap = physical_snapshot()
            report['before'] = snap
            save(marker, report)
            assert snap['allObservedEnginesIdle'], 'Board busy; do not reset active work'
        if args.phase == 'load':
            command(out, 'load', ['tools/run_xsct.py', 'tools/download_dap_fpga.tcl',
                    pair / 'application.elf', pair / 'probe.bit', pair / 'ps7_init.tcl'])
        if args.phase in ['inspect', 'load']:
            command(out, args.phase + '-identity', ['tools/verify_probe_ocm_code.py', '--elf',
                    pair / 'application.elf', '--out-dir', out / (args.phase + '-identity')])
            report['target'] = target_snapshot()
            report['clockAtSafeSpeed'] = live_clock_snapshot()
            report['after'] = physical_snapshot()
        elif args.phase == 'jtag':
            assert args.pair != 'fixed', 'SWD-only diagnostic pair'
            command(out, 'jtag-fixture', ['tools/run_f103_jtag_fixture.py', '--restore-swj', '2',
                    '--output', out / 'jtag-fixture.json', '--', sys.executable, __file__,
                    '--pair', args.pair, '--out', out, '--phase', 'jtag-child'])
        else:
            # Each suite begins with an independent identity check.
            command(out, args.phase + '-identity', ['tools/verify_probe_ocm_code.py', '--elf',
                    pair / 'application.elf', '--out-dir', out / (args.phase + '-identity')])
            transport = 'swd' if args.phase == 'swd' else 'jtag'
            report['beforeTarget'] = target_snapshot()
            save(marker, report)
            speeds = [33333333, 66666666] if args.pair == 'fixed' else [50000000, 60000000]
            for speed in speeds:
                label = f'{transport}-sram-{speed}'
                command(out, label, ['tools/h743_peak.py', '--transport', transport,
                        '--bootstrap-speed-khz', '1000', '--jtag-ir', '4,5', '--speed-hz', speed,
                        '--address', '0x20008000', '--words', '512', '--depth', '32', '--loops', '256',
                        '--repeats', '3', '--soak-seconds', '10', '--output', out / (label + '.json'), *common])
                result = json.loads((out / (label + '.json')).read_text())
                assert result.get('passed') and result.get('restore_match'), result
                assert abs(result['SWCLK_Hz'] - speed) < 10, 'SRAM rate silently changed'
                etm_rtt(out, common, speed, transport, False)
                if not int(report['beforeTarget']['ETMCR'], 16) & 0x400:
                    etm_rtt(out, common, speed, transport, True)
                hss_frontier(out, common, speed, transport)
            report['afterTarget'] = target_snapshot()
            report['after'] = physical_snapshot()
            assert report['after']['allObservedEnginesIdle']
        report['completed'] = True
    except BaseException as exc:
        report['failure'] = repr(exc)
        raise
    finally:
        report['endedAtUtc'] = datetime.now(timezone.utc).isoformat()
        save(marker, report)


if __name__ == '__main__':
    main()
