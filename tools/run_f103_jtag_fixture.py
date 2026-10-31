"""Temporarily enable F103 JTAG around one RAM-only board regression.

The currently loaded CDC target calls SWJ_NOJTAG. SWJ_CFG is not a reliable
readback field, so its restoration value must be supplied from the target source.
No reset or Flash programming is performed. The child owns USB exclusively.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import usb.util
from dap_pipeline_bench import open_dap, setup
from probe_stream import Probe
from test_probe_board import Memory, stop

DHCSR = 0xE000EDF0
APB2ENR = 0x40021018
MAPR = 0x40010004
SWJ_MASK = 7 << 24


def connect():
    dev, out, inp = open_dap()
    probe = Probe()
    try:
        stop(probe, dev)
        setup(out, inp, 50000, 'swd')
        return dev, probe, out, inp, Memory(out, inp)
    except BaseException:
        probe.close()
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)
        raise


def close(dev, probe):
    probe.close()
    usb.util.release_interface(dev, 0)
    usb.util.dispose_resources(dev)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore-swj', type=int, choices=[0, 1, 2], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('a child command is required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    state = dict(command=command, restore_swj_from_target_source=args.restore_swj)
    initial = enabled = mapr = None
    try:
        dev, probe, out, inp, mem = connect()
        try:
            initial = mem.word(DHCSR)
            mem.write_word(DHCSR, 0xA05F0003)
            assert mem.word(DHCSR) & (1 << 17)
            enabled = mem.word(APB2ENR)
            mem.write_word(APB2ENR, enabled | 1)
            mapr = mem.word(MAPR) & ~SWJ_MASK
            state.update(initial_DHCSR=hex(initial), APB2ENR=hex(enabled),
                         MAPR_readable_bits=hex(mapr), target_id=hex(mem.word(0xE0042000)),
                         RCC_before=[mem.word(0x40021000), mem.word(0x40021004)])
            args.output.write_text(json.dumps(state, indent=2) + '\n')
            mem.write_word(MAPR, mapr)
            identity = setup(out, inp, 1000, 'jtag')
            state['JTAG_IDCODE'] = hex(int.from_bytes(identity[2:6], 'little'))
            assert mem.word(0xE000ED00) & 0xFF0FFFF0 == 0x410FC230
            setup(out, inp, 50000, 'swd')
        finally:
            close(dev, probe)
        result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1])
        state['returncode'] = result.returncode
    finally:
        if initial is not None:
            dev, probe, out, inp, mem = connect()
            try:
                mem.write_word(DHCSR, 0xA05F0003)
                if mapr is not None:
                    mem.write_word(MAPR, mapr | (args.restore_swj << 24))
                    state['MAPR_readable_restore_match'] = mem.word(MAPR) & ~SWJ_MASK == mapr
                    assert state['MAPR_readable_restore_match']
                if enabled is not None:
                    mem.write_word(APB2ENR, enabled)
                    state['APB2ENR_restore_match'] = mem.word(APB2ENR) == enabled
                    assert state['APB2ENR_restore_match']
                if 'RCC_before' in state:
                    state['RCC_after'] = [mem.word(0x40021000), mem.word(0x40021004)]
                    assert state['RCC_before'] == state['RCC_after']
                if not initial & (1 << 17):
                    mem.write_word(DHCSR, 0xA05F0001)
                state['run_halt_restore_match'] = bool(mem.word(DHCSR) & (1 << 17)) == bool(initial & (1 << 17))
                assert state['run_halt_restore_match']
            finally:
                close(dev, probe)
        args.output.write_text(json.dumps(state, indent=2) + '\n')
    raise SystemExit(state['returncode'])


if __name__ == '__main__':
    main()
