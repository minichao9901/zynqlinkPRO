"""Verify F103ZE PE2..PE7 wiring one GPIO at a time.

The target is driven through the existing SWD DAP. The Zynq FPGA inputs are
observed independently through the xc7z020 boundary-scan SAMPLE register via
XSCT. No Flash write is performed. GPIO, DBGMCU, clock-enable and halt/run
state are restored in a finally block.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import usb.util
from dap_pipeline_bench import open_dap, setup
from test_probe_board import Memory
from jtag_internal_trace import run

GPIOE_CRL = 0x40011800
GPIOE_IDR = 0x40011808
GPIOE_ODR = 0x4001180C
RCC_APB2ENR = 0x40021018
DBGMCU_CR = 0xE0042004
DHCSR = 0xE000EDF0

# Boundary register positions are from Vivado 2018.3 xc7z020_clg400.bsd.
FPGA_PINS = {
    'PE2_TRACECLK': ('H16', 400),
    'PE3_D0': ('H15', 364),
    'PE4_D1': ('G15', 361),
    'PE5_D2': ('H17', 397),
    'PE6_D3': ('N15', 352),
}
TARGET_BITS = {'PE2_TRACECLK': 1 << 2, 'PE3_D0': 1 << 3,
               'PE4_D1': 1 << 4, 'PE5_D2': 1 << 5,
               'PE6_D3': 1 << 6, 'PE7_UNWIRED': 1 << 7}


def boundary_sample():
    body = r'''jtag targets -set -filter {name =~ "xc7z020"}
set s [jtag sequence]
$s irshift -state IDLE -integer 6 1
$s drshift -capture -state IDLE -tdi 0 1077
$s irshift -state IDLE -integer 6 63
set b [$s run -bits -single]
puts "BOUNDARY $b"
$s delete'''
    text = run(body)
    m = re.search(r'BOUNDARY ([01]{1077})', text)
    if not m:
        raise RuntimeError('xc7z020 boundary SAMPLE response missing')
    bits = m.group(1)
    return {name: int(bits[pos]) for name, (_, pos) in FPGA_PINS.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed-khz', type=int, default=1000)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    saved = {}
    rows = []
    was_halted = False
    try:
        setup(out, inp, args.speed_khz)
        for address in (DHCSR, DBGMCU_CR, RCC_APB2ENR):
            saved[address] = mem.word(address)
        was_halted = bool(saved[DHCSR] & (1 << 17))
        mem.write_word(DHCSR, 0xA05F0003)
        mem.write_word(RCC_APB2ENR, saved[RCC_APB2ENR] | (1 << 6))
        saved[GPIOE_CRL] = mem.word(GPIOE_CRL)
        saved[GPIOE_ODR] = mem.word(GPIOE_ODR)
        mem.write_word(DBGMCU_CR, saved[DBGMCU_CR] & ~0xE0)
        crl = saved[GPIOE_CRL]
        for pin in range(2, 8):
            crl = (crl & ~(0xF << (pin * 4))) | (0x2 << (pin * 4))
        mem.write_word(GPIOE_CRL, crl)
        for name, bit in TARGET_BITS.items():
            # Leave unrelated PE0/PE1/PE8..PE15 outputs unchanged.
            mem.write_word(GPIOE_ODR, (saved[GPIOE_ODR] & ~0xFC) | bit)
            observed = boundary_sample()
            expected = {n: int(n == name) for n in FPGA_PINS}
            target_idr = mem.word(GPIOE_IDR) & 0xFC
            rows.append({'target_pin': name, 'odr': hex(bit),
                         'target_idr': hex(target_idr),
                         'observed_fpga': observed, 'expected_fpga': expected,
                         'pass': observed == expected and target_idr == bit})
            print(rows[-1], flush=True)
        report = {'target': 'STM32F103ZE', 'speed_khz': args.speed_khz,
                  'mapping': {k: v[0] for k, v in FPGA_PINS.items()},
                  'unwired': ['PE7'], 'rows': rows,
                  'all_connected_pins_pass': all(r['pass'] for r in rows[:5]),
                  'pe7_isolated': rows[5]['observed_fpga'] == {n: 0 for n in FPGA_PINS}}
    finally:
        try:
            if GPIOE_ODR in saved and GPIOE_CRL in saved:
                mem.write_word(GPIOE_ODR, saved[GPIOE_ODR])
                mem.write_word(GPIOE_CRL, saved[GPIOE_CRL])
                if 'report' in locals():
                    report['gpio_restored'] = (mem.word(GPIOE_ODR) == saved[GPIOE_ODR]
                                               and mem.word(GPIOE_CRL) == saved[GPIOE_CRL])
            if DBGMCU_CR in saved:
                mem.write_word(DBGMCU_CR, saved[DBGMCU_CR])
            if RCC_APB2ENR in saved:
                mem.write_word(RCC_APB2ENR, saved[RCC_APB2ENR])
            if DHCSR in saved:
                mem.write_word(DHCSR, 0xA05F0003 if was_halted else 0xA05F0001)
        finally:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if 'report' in locals():
                args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)
    if not report['all_connected_pins_pass'] or not report['pe7_isolated'] or not report.get('gpio_restored'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
