"""Reproduce the archived H743 USB/JTAG baseline using backed-up AXI SRAM."""

import argparse
import hashlib
import json
import random
import statistics
import struct
import sys
import time
from pathlib import Path

import usb.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from board_acceptance_target import verify_h743_viewer_rates, wait_for
from dap_pipeline_bench import le, open_dap, read_exact, send, setup, xfer
from h743_peak import ap_select
from probe_build_info import provenance, swd_clock_details
from target_snapshot import same_clock_configuration, snapshot
from test_probe_board import Memory
from test_swd_lowfreq_board import recover

BASE = 0x24050000
SIZE = 4096
RCC = 0x58024400
VOS = 0x58024818
SUPPLY = 0x5802480C
ODEN = 0x5800042C
DHCSR = 0xE000EDF0
FREQUENCY = 66_666_666


def require(test, detail):
    if not test:
        raise RuntimeError(detail)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ClockFixture:
    def __init__(self, mem):
        self.mem = mem
        self.saved = {}
        self.oden = None

    def wait(self, address, mask, value):
        wait_for(lambda: self.mem.word(address), lambda v: v & mask == value, 2,
                 f'{address:#x} mask {mask:#x} expected {value:#x}')

    def enable(self, report, archive):
        m = self.mem
        initial = snapshot(m)
        require(initial['device'] == '0x20036450', '480 MHz fixture requires the H743 rev. V target')
        addresses = (RCC, RCC + 0x10, RCC + 0x18, RCC + 0x1C, RCC + 0x20,
                     RCC + 0x28, RCC + 0x2C, RCC + 0x30, RCC + 0xF4, VOS, SUPPLY)
        s = {a: m.word(a) for a in addresses}
        require(s[RCC + 0x10] & 0x3F == 0 and s[RCC] & 0x3F070000 == 0
                and s[RCC] & 5 == 5 and s[SUPPLY] & 3 == 2,
                'Expected HSI, disabled HSE/PLLs and LDO supply')
        require(int(initial['registers']['0x52002000'], 16) & 0xF >= 4,
                'Existing Flash latency is insufficient for 480/240 MHz')
        self.saved = s
        report['clock_fixture_backup'] = {hex(a): hex(v) for a, v in s.items()}
        archive()
        m.write_word(RCC + 0xF4, s[RCC + 0xF4] | 2)
        self.oden = m.word(ODEN)
        report['clock_fixture_overdrive_before'] = hex(self.oden)
        archive()
        # The board is already wired for the internal LDO. Latch that
        # configuration without changing the supply mode or other CR3 bits.
        if s[SUPPLY] & 4:
            m.write_word(SUPPLY, s[SUPPLY] & ~4)
        self.wait(SUPPLY, 7, 2)
        self.wait(0x58024804, 0x2000, 0x2000)
        m.write_word(VOS, (s[VOS] & ~0xC000) | 0xC000)
        self.wait(VOS, 0xE000, 0xE000)
        m.write_word(ODEN, self.oden | 1)
        self.wait(ODEN, 1, 1)
        self.wait(VOS, 0xE000, 0xE000)
        self.wait(0x58024804, 0x2000, 0x2000)
        m.write_word(RCC, s[RCC] | (1 << 16))
        self.wait(RCC, 1 << 17, 1 << 17)
        m.write_word(RCC + 0x18, 0x48)  # CPU /1, AHB /2, APB3 /2
        m.write_word(RCC + 0x1C, 0x440)  # APB1 and APB2 /2
        m.write_word(RCC + 0x20, 0x50)  # APB4 /4
        m.write_word(RCC + 0x28, (s[RCC + 0x28] & ~0x3F3) | 0x52)
        m.write_word(RCC + 0x2C, (s[RCC + 0x2C] & ~0xF) | 0x10008)
        m.write_word(RCC + 0x30, 0x010102BF)  # HSE25 /5 *192 /2
        m.write_word(RCC, s[RCC] | (1 << 16) | (1 << 24))
        self.wait(RCC, 1 << 25, 1 << 25)
        m.write_word(RCC + 0x10, s[RCC + 0x10] | 3)
        self.wait(RCC + 0x10, 0x38, 0x18)
        report.update(verify_h743_viewer_rates(m))
        report['target_clock_active'] = snapshot(m)

    def restore(self):
        if not self.saved:
            return True
        m, s = self.mem, self.saved
        m.write_word(RCC + 0x10, s[RCC + 0x10])
        self.wait(RCC + 0x10, 0x38, 0)
        m.write_word(RCC, s[RCC])
        self.wait(RCC, 0x02020000, 0)
        for offset in (0x18, 0x1C, 0x20, 0x28, 0x2C, 0x30):
            m.write_word(RCC + offset, s[RCC + offset])
        if self.oden is not None:
            m.write_word(ODEN, self.oden)
            self.wait(ODEN, 1, self.oden & 1)
        m.write_word(VOS, s[VOS])
        self.wait(VOS, 0xE000, (s[VOS] & 0xC000) | 0x2000)
        m.write_word(RCC + 0xF4, s[RCC + 0xF4])
        return m.word(SUPPLY) == s[SUPPLY] & ~4 and m.word(RCC + 0xF4) == s[RCC + 0xF4]


def bench(mem, idle, soak, modes, hz, sampling, observation):
    tx, rx = mem.out, mem.inp
    require(xfer(tx, rx, [4, idle, 64, 0, 0, 0]) == b'\x04\x00', 'idle rejected')
    require(xfer(tx, rx, [0x8D, 255])[2] == idle, 'idle readback mismatch')
    require(xfer(tx, rx, [0x11, *le(hz)]) == b'\x11\x00', 'clock rejected')
    mode_reply = xfer(tx, rx, [0x89, sampling])
    require(xfer(tx, rx, [0x89, 255])[2] == sampling, f'sample mode mismatch: {mode_reply.hex()}')
    require(xfer(tx, rx, [0x16, 0]) == bytes.fromhex('16007704a06b'), '66 MHz IDCODE mismatch')
    fclk, cfg = struct.unpack_from('<II', xfer(tx, rx, [0x80, 255]), 4)
    tck = swd_clock_details(fclk, cfg)['SWCLK_Hz']
    require(abs(tck - hz) <= 2, f'actual TCK {tck:g}, FCLK {fclk}')
    observation.update(idle=idle, fclk_hz=fclk, tck_hz=tck, mode=sampling, cfg=hex(cfg))
    current = mem.read(BASE, 1024)
    guards = mem.read(BASE + 1024, 3072)
    rng = random.Random(743)
    patterns = [rng.randbytes(1024) for _ in range(2)]
    samples = {mode: [] for mode in modes}
    words, depth, blocks = 512, 32, 64
    start = time.perf_counter()
    while len(samples[modes[0]]) < 3 or time.perf_counter() - start < soak:
        for mode in modes:
            if mode == 'write':
                current = patterns[len(samples['write']) % len(patterns)]
            ap_select(tx, rx, BASE)
            header = bytes([6, 0, words & 255, words >> 8, 0x0F if mode == 'read' else 0x0D])
            expected = bytes([6, words & 255, words >> 8, 1]) + (current * 2 if mode == 'read' else b'')
            packet = header + (current * 2 if mode == 'write' else b'')
            t0 = time.perf_counter()
            for _ in range(blocks // depth):
                for _ in range(depth):
                    send(tx, packet)
                for _ in range(depth):
                    reply = read_exact(rx, len(expected))
                    require(reply == expected, f'{mode} mismatch: {reply[:16].hex()}, '
                            f'after {len(samples[mode])} complete rounds')
            elapsed = time.perf_counter() - t0
            samples[mode].append(blocks * words * 4 / elapsed / 1e6)
            observation[mode] = dict(completed=len(samples[mode]), last_MB_s=samples[mode][-1])
    require(mem.read(BASE + 1024, 3072) == guards, 'adjacent AXI SRAM changed')
    require(mem.read(BASE, 1024) == current, 'final AXI SRAM verification differs')
    return dict(idle=idle, fclk_hz=fclk, tck_hz=tck, mode=sampling, cfg=hex(cfg), depth=depth,
                words=words, blocks=blocks, seconds=time.perf_counter() - start,
                rounds=len(samples[modes[0]]), directions={
                    mode: dict(median=statistics.median(values), minimum=min(values), max=max(values))
                    for mode, values in samples.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--target-480', action='store_true')
    parser.add_argument('--soak', type=float, default=60)
    parser.add_argument('--idle', type=int, nargs='+', default=(3, 5))
    parser.add_argument('--directions', choices=('read', 'write'), nargs='+', default=('write', 'read'))
    parser.add_argument('--hz', type=int, default=FREQUENCY)
    parser.add_argument('--sampling', type=int, default=16)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(f'JTAG66/idle 3 and 5, serial {args.serial}, RAM {BASE:#x}+{SIZE}, target 480={args.target_480}')
        return
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(rows=[], phase='preflight', data_size=SIZE, address=hex(BASE),
                  artifacts=provenance('prebuilt/release-20261106/probe.bit',
                                       'prebuilt/h743-jtag66-20261109/application.elf'))

    def archive():
        (args.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')

    saved = guards = initial_dhcsr = None
    dev, tx, rx = open_dap(args.serial)
    mem = Memory(tx, rx)
    fixture = ClockFixture(mem)
    try:
        require(setup(tx, rx, 10000, 'jtag') == bytes.fromhex('16007704a06b'), 'wrong TAP')
        report['target_before'] = snapshot(mem)
        require(report['target_before']['device'] == '0x20036450', 'wrong H743 device')
        require(mem.word(0xE000ED14) & (1 << 16) == 0, 'D-cache enabled')
        initial_dhcsr = mem.word(DHCSR)
        report['dhcsr_before'] = hex(initial_dhcsr)
        mem.write_word(DHCSR, 0xA05F0003)
        fixture.wait(DHCSR, 1 << 17, 1 << 17)
        guards = mem.read(BASE - 4, 4) + mem.read(BASE + SIZE, 4)
        copy = mem.read(BASE, SIZE)
        require(mem.read(BASE, SIZE) == copy, 'double-read backup differs')
        (args.out / 'backup.bin').write_bytes(copy)
        (args.out / 'guards.bin').write_bytes(guards)
        saved = copy
        report['backup_sha256'] = sha(saved)
        report['phase'] = 'clock'
        archive()
        if args.target_480:
            fixture.enable(report, archive)
        if args.directions == ['read']:
            pattern = random.Random(743).randbytes(1024)
            mem.write(BASE, pattern)
            require(mem.read(BASE, len(pattern)) == pattern, '10 MHz preload failed')
        for idle in args.idle:
            report['phase'] = f'idle{idle}'
            report['observation'] = {}
            archive()
            row = bench(mem, idle, args.soak, args.directions, args.hz, args.sampling,
                        report['observation'])
            report['rows'].append(row)
            print(json.dumps(row), flush=True)
            archive()
        report['phase'] = 'complete'
    except Exception as exc:
        report['error'] = repr(exc)
        raise
    finally:
        try:
            recover(dev, rx)
            setup(tx, rx, 10000, 'jtag')
            require(snapshot(mem)['device'] == '0x20036450', 'lost H743 before restore')
            if saved is not None:
                if mem.read(BASE, SIZE) != saved:
                    mem.write(BASE, saved)
                restored = mem.read(BASE, SIZE)
                report['restore_sha256'] = sha(restored)
                report['ram_restored'] = restored == saved
                report['guards_match'] = mem.read(BASE - 4, 4) + mem.read(BASE + SIZE, 4) == guards
            try:
                report['voltage_restored'] = fixture.restore()
                report['supply_after'] = hex(mem.word(SUPPLY))
                report['target_after'] = snapshot(mem)
                report['rcc_restored'] = same_clock_configuration(report['target_before'], report['target_after'])
            finally:
                if initial_dhcsr is not None:
                    mem.write_word(DHCSR, 0xA05F0000 | (initial_dhcsr & 0x2F))
                    report['dhcsr_after'] = hex(mem.word(DHCSR))
                    report['core_state_restored'] = (int(report['dhcsr_after'], 16) ^ initial_dhcsr) & 0x2002F == 0
                xfer(tx, rx, [0x89, 0])
                require(xfer(tx, rx, [0x89, 255])[2] == 0, 'sample reset failed')
                require(xfer(tx, rx, [3]) == b'\x03\x00', 'disconnect failed')
        except Exception as exc:
            report['restore_error'] = repr(exc)
            raise
        finally:
            usb.util.dispose_resources(dev)
            archive()
    require(all(report.get(k) for k in ('ram_restored', 'guards_match', 'voltage_restored',
                                       'rcc_restored', 'core_state_restored')), 'restore validation failed')


if __name__ == '__main__':
    main()
