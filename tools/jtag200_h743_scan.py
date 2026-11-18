"""Check ARM TAP and posted SRAM reads at high TCK using the J200 raw PHY."""

import argparse
import itertools
import json
import struct
from pathlib import Path

from jtag200 import PROFILES, bits
from jtag200_ram_stress import PhysicalPort, Ownership, append_data, pack, require, value_at

IDCODE = 0x6BA00477
BASE = 0x24050000


class Scan:
    def __init__(self, reset=True):
        # SWJ select, reset both TAPs, then enter Run-Test/Idle.
        self.tms = [1] * 64 + bits(0xE73C, 16) + bits(0x1F, 8) if reset else []
        self.tdi = [0] * len(self.tms)

    def instruction(self, value):
        # Four-bit ARM DAP first in the scan stream and five-bit boundary TAP
        # set to BYPASS. DR scans thus carry one extra bit after the DAP.
        self.tms += [1, 1, 0, 0] + [0] * 8 + [1, 1, 0]
        self.tdi += [0] * 4 + bits(value | 0x1F0, 9) + [0, 0]

    def data(self, request, value, idle):
        return append_data(self.tms, self.tdi, (value << 3) | request, 36, idle)

    def identify(self):
        self.instruction(14)
        return append_data(self.tms, self.tdi, 0, 33, 0)

    def transfer(self, port, half, advance):
        words = pack(self.tms, self.tdi, half, advance, advance)
        return port.scan(struct.pack(f'<{len(words)}I', *words), len(words))


def slow_read(port, half, advance, address, count, phases):
    """Keep JTAG transactions separate so AP latency cannot affect sampling."""
    def step(ir, request, value=0):
        scan = Scan(reset=False)
        if ir:
            scan.instruction(ir)
        start = scan.data(request, value, 2)
        frame = scan.transfer(port, half, advance)
        return {phase: value_at(frame, half, start, 35, phase) for phase in phases}

    setup = [
        step(10, 2, 0x50000032), step(None, 3), step(None, 4),
        step(11, 0, 0x23000052), step(None, 2, address), step(None, 7),
    ]
    data = [step(None, 7) for _ in range(count - 1)]
    data.append(step(10, 7))    # RDBUFF captures the final posted AP response
    fence = [step(None, 3), step(None, 7)]
    return {
        phase: dict(values=[packet[phase] for packet in data],
                    acks=[packet[phase] & 7 for packet in setup + data + fence],
                    status=fence[-1][phase] >> 3)
        for phase in phases
    }


def select(port, rate, tap):
    index, half, hz = PROFILES[rate]
    port.command(f'profile {index} {tap} {hz} {half}')
    return half, hz


def identify(port, half, rounds):
    advance = int(half == 2)
    scan = Scan()
    start = scan.identify()
    identity = set(range(12, 59))
    for _ in range(rounds):
        raw = scan.transfer(port, half, advance)
        identity &= {phase for phase in identity
                     if value_at(raw, half, start, 32, phase) == IDCODE}
        if not identity:
            break
    return identity


def shift_only(port, rate, tap):
    """Set up Shift-DR at 50 MHz, then shift IDCODE at the tested TCK."""
    common = set(range(60))
    errors = []
    for _ in range(3):
        select(port, '50', 16)
        enter = Scan()
        enter.instruction(14)
        enter.tms.extend((1, 0, 0))
        enter.tdi.extend((0, 0, 0))
        enter.transfer(port, 4, 0)
        half, hz = select(port, rate, tap)
        shift = Scan(reset=False)
        shift.tms = shift.tdi = [0] * 33
        raw = shift.transfer(port, half, 0)
        received = [value_at(raw, half, 0, 32, ph) for ph in range(60)]
        common &= {ph for ph, value in enumerate(received) if value == IDCODE}
        errors.append(min((value ^ IDCODE).bit_count() for value in received))
    return dict(rate=rate, nominal_tck_hz=hz, tap=tap, sample_slots=sorted(common),
                minimum_error_bits=errors)


def inspect(port, rate, tap, addresses, rounds):
    half, hz = select(port, rate, tap)
    advance = int(half == 2)
    idcode = identify(port, half, rounds)
    hits = set(idcode)
    details = {}
    for address, expected in addresses:
        if not hits:
            break
        for attempt in range(2):
            values = slow_read(port, half, advance, address, len(expected), hits)
            hits &= {phase for phase in hits
                     if values[phase]['values'] == [value << 3 | 2 for value in expected]
                     and all(ack == 2 for ack in values[phase]['acks'])
                     and values[phase]['status'] & 0xA2 == 0}
            if not hits:
                details[hex(address)] = dict(attempt=attempt+1, observed=values)
                break
        else:
            details[hex(address)] = sorted(hits)
    return dict(rate=rate, tap=tap, idle=2, nominal_tck_hz=hz, idcode_rounds=rounds,
                IDCODE_slots=sorted(idcode), data_slots=sorted(hits),
                fclk_control=port.command('read_word 0xf8000180'), responses=details)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', required=True, type=Path)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--cable-serial', required=True)
    parser.add_argument('--sdk', default=Path('E:/Xilinx/SDK/2018.3'), type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--dense-200', action='store_true', help='Sweep all 32 receive taps at 200 MHz')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print('Read ARM TAP/CPUID/DBGMCU and fixed AXI SRAM via the 50/100/200 MHz raw PHY.')
        return
    saved = args.backup.read_bytes()
    require(len(saved) == 4096, 'Need the live H743 AXI SRAM baseline snapshot')
    read_set = [(0xE000ED00, (0x411FC271,)), (0x5C001000, (0x20036450,))]
    words = struct.unpack_from('<2I', saved)
    long_check = read_set + [(BASE, words)]
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(rows=[], shift_only=[], sessions='physical MEM-AP0 raw scans with gaps')

    def archive():
        (args.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')

    lock = Ownership()
    try:
        port = PhysicalPort(args.out, args.cable_serial, args.sdk)
        try:
            report['probe'] = port.verify_probe(args.pair)
            taps = (0, 8, 16, 24, 31)
            nominal_points = itertools.product(('50', '80', '100', '160', '200'), taps)
            shift_points = itertools.product(('160', '200'), taps)
            if args.dense_200:
                nominal_points = shift_points = [('200', tap) for tap in range(32)]
            for rate, tap in nominal_points:
                row = inspect(port, rate, tap, long_check, 3)
                report['rows'].append(row)
                print(json.dumps({k: v for k, v in row.items() if k != 'responses'}), flush=True)
                archive()
            for rate, tap in shift_points:
                report['shift_only'].append(shift_only(port, rate, tap))
                archive()
        finally:
            try:
                restored = inspect(port, '50', 16, long_check, 3)
                report['verify_after'] = restored
            finally:
                port.close()
                archive()
    finally:
        lock.close()


if __name__ == '__main__':
    main()
