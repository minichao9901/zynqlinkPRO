"""Bounded follow-up diagnostics; preserve target RAM, clocks and trace state."""
import argparse
from pathlib import Path
import struct
import time

import usb.util
from dap_pipeline_bench import open_dap, setup, xfer
from test_probe_board import Memory
from test_swd_lowfreq_board import recover
from validate_fclk_performance import (ROOT, PAIRS, command, save, etm_rtt,
                                       physical_snapshot)


def profiles(out):
    d, o, i = open_dap()
    m = Memory(o, i)
    report = dict(rows=[], writesOnlyProbeSampling=True, targetWrites=False)
    try:
        setup(o, i, 1000)
        report['targetBefore'] = {
            'RCC': [m.word(0x40021000), m.word(0x40021004)],
            'ETMCR': hex(m.word(0xe0041000)), 'DHCSR': hex(m.word(0xe000edf0))}
        for phase in [0, 1]:
            for boundary in [0, 1]:
                row = dict(phase=phase, boundary=boundary, passed=False,
                           dpReads=0, cpuidReads=0)
                try:
                    setup(o, i, 33333, speed_hz=33333333)
                    assert xfer(o, i, [0x80, phase])[1] == 0
                    assert xfer(o, i, [0x8a, boundary])[1] == 0
                    diag = xfer(o, i, [0x80, 255])
                    row['FCLK_Hz'], cfg = struct.unpack_from('<II', diag, 4)
                    row['cfg'] = hex(cfg)
                    assert row['FCLK_Hz'] == 133333332
                    for _ in range(128):
                        reply = xfer(o, i, [5, 0, 1, 2])
                        assert reply[:3] == bytes([5, 1, 1]) and int.from_bytes(reply[3:7], 'little') == 0x1ba01477, reply.hex()
                        row['dpReads'] += 1
                    for _ in range(128):
                        assert m.word(0xe000ed00) == 0x411fc231
                        row['cpuidReads'] += 1
                    row['passed'] = True
                except Exception as exc:
                    row['error'] = repr(exc)
                finally:
                    recover(d, i)
                    setup(o, i, 1000)
                    report['rows'].append(row)
                    save(out / 'profiles.json', report)
                    print('PROFILE', row, flush=True)
        report['targetAfter'] = {'RCC': [m.word(0x40021000), m.word(0x40021004)],
            'ETMCR': hex(m.word(0xe0041000)), 'DHCSR': hex(m.word(0xe000edf0))}
        assert report['targetAfter']['RCC'] == report['targetBefore']['RCC']
        assert report['targetAfter']['ETMCR'] == report['targetBefore']['ETMCR']
    finally:
        usb.util.dispose_resources(d)
        save(out / 'profiles.json', report)


def trace_rtt(out, pair_name, speeds, transport):
    pair = ROOT / 'prebuilt' / PAIRS[pair_name]
    common = ['--bit', pair / 'probe.bit', '--elf', pair / 'application.elf']
    # The same ETMv3 / parallel TPIU configuration as test_orbtrace_board.py.
    regs = {'DEMCR': 0xe000edfc, 'DBG_CR': 0xe0042004, 'ETMCR': 0xe0041000,
            'TRIGGER': 0xe0041008, 'TEEVR': 0xe0041020, 'TECR1': 0xe0041024,
            'FFLR': 0xe004102c, 'TRACEID': 0xe0041200,
            'CSPSR': 0xe0040004, 'SPPR': 0xe00400f0, 'FFCR': 0xe0040304}
    report = dict(targetFlashWrites=False, targetClockWrites=False,
                  purpose='RTT with explicit active ETM output, then programming pause',
                  before={}, after={})
    d, o, i = open_dap()
    m = Memory(o, i)
    locks = {}
    before = report['before']
    cr = None
    try:
        setup(o, i, 1000)
        report['RCC_before'] = [m.word(0x40021000), m.word(0x40021004)]
        report['GPIOE_CRL'] = hex(m.word(0x40011800))
        assert m.word(0x40011800) & 0x0fffff00 == 0x0bbbbb00, 'Trace pins need existing AF_PP50 configuration'
        for name, address in regs.items():
            before[name] = m.word(address)
        save(out / 'trace-rtt.json', report)
        for base in [0xe0041000, 0xe0040000]:
            locks[base] = m.word(base + 0xfb4)
            if locks[base] & 3 == 3:
                m.write_word(base + 0xfb0, 0xc5acce55)
        m.write_word(regs['DEMCR'], before['DEMCR'] | 0x1000000)
        m.write_word(regs['DBG_CR'], (before['DBG_CR'] & ~0xe0) | 0xe0)
        cr = (before['ETMCR'] | 0xc00) & ~0x301
        m.write_word(regs['ETMCR'], cr)

        def wait_program(want):
            for _ in range(100):
                if m.word(0xe0041010) & 2 == want:
                    return
                time.sleep(.001)
            raise RuntimeError('ETM programming handshake failed')

        wait_program(2)
        for name, value in {'TRIGGER': 0, 'TEEVR': 0x6f, 'TECR1': 0, 'FFLR': 0,
                            'TRACEID': 2, 'CSPSR': 8, 'SPPR': 0,
                            'FFCR': before['FFCR'] | 2}.items():
            m.write_word(regs[name], value)
        m.write_word(regs['ETMCR'], cr & ~0x400)
        wait_program(0)
        report['configured'] = {n: hex(m.word(a)) for n, a in regs.items()}
        report['ETMSR_enabled'] = hex(m.word(0xe0041010))
        save(out / 'trace-rtt.json', report)
        usb.util.dispose_resources(d)
        d = None
        for speed in speeds:
            etm_rtt(out, common, speed, transport, False)
            etm_rtt(out, common, speed, transport, True)
        report['completed'] = True
    finally:
        if d is None:
            d, o, i = open_dap()
            setup(o, i, 1000)
            m = Memory(o, i)
        try:
            if cr is not None:
                m.write_word(regs['ETMCR'], cr)
                wait_program(2)
                for name, value in before.items():
                    if name not in ['ETMCR', 'DEMCR', 'DBG_CR']:
                        m.write_word(regs[name], value)
                m.write_word(regs['ETMCR'], before['ETMCR'])
                m.write_word(regs['DBG_CR'], before['DBG_CR'])
                m.write_word(regs['DEMCR'], before['DEMCR'])
                report['after'] = {n: m.word(a) for n, a in regs.items()}
                report['registers_restored'] = report['after'] == before
                assert report['registers_restored'], report
            for base, lock in locks.items():
                if lock & 3 == 3:
                    m.write_word(base + 0xfb0, 0)
            report['RCC_after'] = [m.word(0x40021000), m.word(0x40021004)]
            assert report['RCC_after'] == report['RCC_before']
        finally:
            usb.util.dispose_resources(d)
            save(out / 'trace-rtt.json', report)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair', choices=list(PAIRS), required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--kind', choices=['profiles', 'trace-rtt'], required=True)
    p.add_argument('--speeds', default='50000000,60000000')
    p.add_argument('--transport', choices=['swd', 'jtag'], default='swd')
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pair = ROOT / 'prebuilt' / PAIRS[a.pair]
    command(out, 'identity', ['tools/verify_probe_ocm_code.py', '--elf', pair / 'application.elf',
                             '--out-dir', out / 'identity'])
    if a.kind == 'profiles':
        assert a.pair == 'fixed'
        profiles(out)
    else:
        trace_rtt(out, a.pair, list(map(int, a.speeds.split(','))), a.transport)
    save(out / 'final-safety.json', physical_snapshot())


if __name__ == '__main__':
    main()
