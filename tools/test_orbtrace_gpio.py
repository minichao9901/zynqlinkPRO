"""Drive known TPIU frames from F103ZE GPIOE through the real trace wires.

Runs with the target halted, snapshots GPIO and run state, and restores both.
Reads PL records through Zynq JTAG to separate pin reception from USB transfer.
"""
import json
import argparse
from pathlib import Path
import re
import usb.util
from dap_pipeline_bench import open_dap, setup
from test_probe_board import Memory
from jtag_internal_trace import run


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--modes', default='3:1000,2:10000,2:1000,3:10000,1:1000')
    ap.add_argument('--raw', action='store_true', help='Expect raw DDR bytes from diagnostic bit')
    args = ap.parse_args()
    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    saved, rows = {}, []

    def byte(value):
        for nibble, edge in [(value & 15, 4), (value >> 4, 4 << 16)]:
            bits = nibble << 3
            mem.write_word(0x40011810, bits | ((0x78 ^ bits) << 16))
            mem.write_word(0x40011810, edge)

    try:
        setup(out, inp, 10000)
        for address in [0xe000edf0, 0xe0042004, 0x40021018, 0x40011800, 0x4001180c]:
            saved[address] = mem.word(address)
        mem.write_word(0xe000edf0, 0xa05f0003)
        mem.write_word(0xe0042004, saved[0xe0042004] & ~0xe0)
        mem.write_word(0x40021018, saved[0x40021018] | 64)
        for item in args.modes.split(','):
            mode, speed = map(int, item.split(':'))
            assert mode in (1, 2, 3) and 0 < speed <= 50000
            setup(out, inp, speed)
            mem.write_word(0x40011800, (saved[0x40011800] & ~0x0fffff00) | (int(str(mode)*5, 16) << 8))
            mem.write_word(0x40011810, 0x7c << 16)
            run('mwr -force 0x40030004 15')
            for _ in range(40):
                byte(0)
            for v in bytes.fromhex('ffffff7f'):
                byte(v)
            for _ in range(2):
                for v in bytes.fromhex('05ab1011121307912021222324250908'):
                    byte(v)
            for _ in range(10):
                byte(0xff)
                byte(0x7f)
            raw = run('puts [format "STATUS %08X" [mrd -force -value 0x40030008]]\n'
                      'set n [mrd -force -value 0x4003000c]\n'
                      'for {set i 0} {$i<$n} {incr i} {puts [format "RECORD %08X" [mrd -force -value 0x40030010]]}\n'
                      'mwr -force 0x40030004 12')
            actual = [int(s, 16) for s in re.findall(r'RECORD ([0-9A-F]{8})', raw)]
            expected = ([0x2ab, *range(0x210, 0x214), 0x291, *range(0x320, 0x326)])*2
            status=int(re.search(r'STATUS ([0-9A-F]+)', raw)[1],16)
            if args.raw:
                sample=bytes(v & 255 for v in actual if v >> 8 == 2)
                shifted=bytes((a >> 4)|((b & 15)<<4) for a,b in zip(sample,sample[1:]))
                pattern=bytes.fromhex('ffffff7f')+bytes.fromhex('05ab1011121307912021222324250908')*2
                found=[j for j,candidate in enumerate((sample,shifted)) if pattern in candidate]
                row=dict(gpio_mode=mode,swd_khz=speed,raw=True,records=len(actual),
                         phase_matches=found,status=f'{status:08X}',
                         match=bool(found) and not(status&4) and all(v>>8==2 for v in actual))
            else:
                row = dict(gpio_mode=mode, swd_khz=speed, expected=expected, records=actual,
                           match=actual == expected and not(status&4), status=f'{status:08X}')
            rows.append(row)
            print({k: v for k, v in row.items() if k not in ('expected', 'records')}, flush=True)
    finally:
        if saved:
            setup(out, inp, 10000)
            for address in [0x4001180c, 0x40011800, 0x40021018, 0xe0042004]:
                mem.write_word(address, saved[address])
            mem.write_word(0xe000edf0, 0xa05f0003 if saved[0xe000edf0] & (1 << 17) else 0xa05f0001)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, indent=2)+'\n')
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)
    if not rows or not all(row['match'] for row in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
