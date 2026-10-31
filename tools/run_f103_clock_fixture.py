"""Run RAM-only benchmarks at a temporary F103 HSE8 x12 clock, then restore.

The application Flash is never programmed or executed at the temporary clock:
the core remains halted except for explicit SRAM producers. USB peripheral
clock is gated while its PLL-derived clock would be invalid. The original
clock/Flash-latency/peripheral clock configuration and run state are restored.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from benchmark_rtt_forward import core_read, core_write
from dap_pipeline_bench import setup, open_dap
from run_f103_jtag_fixture import close, DHCSR
from probe_stream import Probe
from test_probe_board import Memory, stop

CR, CFGR, APB1ENR, FLASH = 0x40021000, 0x40021004, 0x4002101C, 0x40022000


def connect():
    dev, out, inp = open_dap()
    probe = Probe()
    try:
        stop(probe, dev)
        setup(out, inp, 1000, 'swd')
        return dev, probe, out, inp, Memory(out, inp)
    except BaseException:
        close(dev, probe)
        raise


def wait_bits(mem, address, mask, value):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        actual = mem.word(address)
        if actual & mask == value:
            return actual
        time.sleep(.001)
    raise RuntimeError(f'clock transition timeout {address:#x}: {actual:#x}')


def hsi(mem):
    mem.write_word(CR, mem.word(CR) | 1)
    wait_bits(mem, CR, 2, 2)
    mem.write_word(CFGR, mem.word(CFGR) & ~3)
    wait_bits(mem, CFGR, 12, 0)


def set96(mem, saved):
    mem.write_word(FLASH, (saved['FLASH_ACR'] & ~7) | 2)
    mem.write_word(APB1ENR, saved['APB1ENR'] & ~(1 << 23))
    hsi(mem)
    mem.write_word(CR, mem.word(CR) & ~(1 << 24))
    wait_bits(mem, CR, 1 << 25, 0)
    mem.write_word(CR, mem.word(CR) | (1 << 16))
    wait_bits(mem, CR, 1 << 17, 1 << 17)
    # SYS/HCLK96, APB1 /2, APB2 /1, ADC /8; preserve MCO/USB prescaler.
    mask = 15 | (15 << 4) | (7 << 8) | (7 << 11) | (3 << 14) | (63 << 16)
    cfg = (saved['CFGR'] & ~mask) | (4 << 8) | (3 << 14) | (1 << 16) | (10 << 18)
    mem.write_word(CFGR, cfg)
    mem.write_word(CR, mem.word(CR) | (1 << 24))
    wait_bits(mem, CR, 1 << 25, 1 << 25)
    mem.write_word(CFGR, cfg | 2)
    value = wait_bits(mem, CFGR, 12, 8)
    assert (value >> 18) & 15 == 10 and not value & 0xF0, hex(value)


def restore(mem, saved):
    hsi(mem)
    mem.write_word(CR, mem.word(CR) & ~(1 << 24))
    wait_bits(mem, CR, 1 << 25, 0)
    mem.write_word(CFGR, saved['CFGR'] & ~15)
    mem.write_word(CR, saved['CR'] | 1)
    if saved['CR'] & (1 << 17):
        wait_bits(mem, CR, 1 << 17, 1 << 17)
    if saved['CR'] & (1 << 25):
        wait_bits(mem, CR, 1 << 25, 1 << 25)
    mem.write_word(CFGR, saved['CFGR'])
    wait_bits(mem, CFGR, 12, saved['CFGR'] & 12)
    mem.write_word(FLASH, saved['FLASH_ACR'])
    mem.write_word(APB1ENR, saved['APB1ENR'])
    mem.write_word(CR, saved['CR'])


def dwt_check(mem, output):
    base = 0x2000F000
    regs = {k: core_read(mem, k) for k in [*range(19), 20]}
    ram = mem.read(base, 4096)
    output.with_suffix('.dwt.backup.bin').write_bytes(ram)
    addresses = [0xE000EDFC, 0xE0001000, 0xE0001004]
    debug = {a: mem.word(a) for a in addresses}
    result = dict(scratch_backup_sha256=hashlib.sha256(ram).hexdigest())
    try:
        mem.write(base, b'\xfe\xe7')  # SRAM-only B .; no stack or peripheral use.
        mem.write_word(addresses[0], debug[addresses[0]] | (1 << 24))
        mem.write_word(addresses[1], debug[addresses[1]] | 1)
        core_write(mem, 16, 0x01000000)
        core_write(mem, 20, 1)
        core_write(mem, 15, base | 1)
        mem.write_word(DHCSR, 0xA05F0001)
        t = time.perf_counter(); a = mem.word(addresses[2]); t0 = (t + time.perf_counter()) / 2
        time.sleep(.35)
        t = time.perf_counter(); b = mem.word(addresses[2]); t1 = (t + time.perf_counter()) / 2
        hz = ((b - a) & 0xFFFFFFFF) / (t1 - t0)
        assert 94_000_000 < hz < 98_000_000, hz
        result.update(elapsed_s=t1-t0, cycles=(b-a) & 0xFFFFFFFF, measured_Hz=hz,
                      method='DWT CYCCNT in SRAM-only loop; host midpoint-bracketed SWD reads')
    finally:
        mem.write_word(DHCSR, 0xA05F0003)
        mem.write_word(addresses[1], debug[addresses[1]])
        mem.write_word(addresses[2], debug[addresses[2]])
        mem.write_word(addresses[0], debug[addresses[0]])
        mem.write(base, ram)
        assert mem.read(base, 4096) == ram
        for k, v in regs.items():
            core_write(mem, k, v)
        assert {k: core_read(mem, k) for k in regs} == regs
        result.update(scratch_restored=True, core_registers_restored=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        p.error('child command required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(command=command, target_Flash_programmed=False, requested_HCLK_Hz=96000000)
    saved = initial = None
    try:
        dev, probe, out, inp, mem = connect()
        try:
            initial = mem.word(DHCSR)
            mem.write_word(DHCSR, 0xA05F0003)
            assert mem.word(0xE0042000) & 0xFFF == 0x414
            setup(out, inp, 1000, 'swd')
            saved = {name: mem.word(a) for name, a in
                     [('CR', CR), ('CFGR', CFGR), ('APB1ENR', APB1ENR), ('FLASH_ACR', FLASH)]}
            report.update(initial_DHCSR=hex(initial), clock_before=saved)
            args.output.write_text(json.dumps(report, indent=2) + '\n')
            set96(mem, saved)
            report['clock_active'] = {name: mem.word(a) for name, a in [('CR', CR), ('CFGR', CFGR)]}
            report['DWT_verification'] = dwt_check(mem, args.output)
            args.output.write_text(json.dumps(report, indent=2) + '\n')
        finally:
            close(dev, probe)
        report['returncode'] = subprocess.run(command, cwd=Path(__file__).resolve().parents[1]).returncode
    finally:
        if saved is not None:
            dev, probe, out, inp, mem = connect()
            try:
                mem.write_word(DHCSR, 0xA05F0003)
                setup(out, inp, 1000, 'swd')
                restore(mem, saved)
                after = {name: mem.word(a) for name, a in
                         [('CR', CR), ('CFGR', CFGR), ('APB1ENR', APB1ENR), ('FLASH_ACR', FLASH)]}
                report['clock_after'] = after
                report['clock_restore_match'] = after == saved
                assert report['clock_restore_match'], (saved, after)
                if not initial & (1 << 17):
                    mem.write_word(DHCSR, 0xA05F0001)
                report['run_halt_restore_match'] = bool(mem.word(DHCSR) & (1 << 17)) == bool(initial & (1 << 17))
                assert report['run_halt_restore_match']
            finally:
                close(dev, probe)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(report['returncode'])


if __name__ == '__main__':
    main()
