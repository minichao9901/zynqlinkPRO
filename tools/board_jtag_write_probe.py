"""Compare scalar and block JTAG writes with independent scalar readback.

For the dual-transport F103 target: halt and save/restore scratch SRAM using
50 MHz SWD scalar transfers, then test JTAG with scalar readback. Load and
hash the intended bit/ELF pair before running.
"""
import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

from dap_pipeline_bench import open_dap, setup, xfer, le

CSW = 0x23000052


def scalar(out, inp, req, value=0):
    packet = [5, 0, 1, req] + ([] if req & 2 else le(value))
    reply = xfer(out, inp, packet)
    assert reply[:3] == b'\x05\x01\x01', reply.hex(' ')
    if req & 2:
        assert len(reply) == 7, reply.hex(' ')
        return int.from_bytes(reply[3:], 'little')


def address(out, inp, addr):
    for req, value in [(8, 0), (1, CSW), (5, addr)]:
        scalar(out, inp, req, value)


def read_scalar(out, inp, addr, count):
    address(out, inp, addr)
    return [scalar(out, inp, 15) for _ in range(count)]


def write_scalar(out, inp, addr, words):
    address(out, inp, addr)
    for word in words:
        scalar(out, inp, 13, word)


def write_words(out, inp, addr, words):
    address(out, inp, addr)
    reply = xfer(out, inp, bytes([6, 0, len(words) & 255, len(words) >> 8, 13])
                 + b''.join(w.to_bytes(4, 'little') for w in words))
    assert reply == bytes([6, len(words) & 255, len(words) >> 8, 1]), reply.hex(' ')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--speed', type=int, default=50000)
    ap.add_argument('--counts', default='1,2,3,4,6,7,8,16,32,64,256')
    ap.add_argument('--base', type=lambda x: int(x, 0), default=0x20004000)
    ap.add_argument('--mode', type=lambda x: int(x, 0), default=None)
    ap.add_argument('--dump-command', action='store_true', help='Read command BRAM through XSCT after each block write')
    ap.add_argument('--idle', type=int, default=None, help='Override idle TCK cycles via XSCT')
    ap.add_argument('--half-delay', type=int, default=0, help='Override PHY half-cycle divider via XSCT')
    ap.add_argument('--batch', action='store_true', help='Also drive the legacy RTL batch engine via XSCT')
    ap.add_argument('--pattern-seed', type=int, default=None, help='Use reproducible random payloads')
    ap.add_argument('--output', type=Path, default=Path('build/jtag_write_probe.json'))
    args = ap.parse_args()
    counts = [int(n) for n in args.counts.split(',')]
    assert counts and min(counts) > 0 and max(counts) <= 256
    assert args.base % 1024 == 0
    dev, out, inp = open_dap()
    report = {'requested_khz': args.speed, 'base': hex(args.base), 'pattern_seed': args.pattern_seed, 'rows': []}
    rng = random.Random(args.pattern_seed)
    backup = initial = None
    try:
        # A marginal JTAG mode must not corrupt the backup or the recovery.
        setup(out, inp, 50000, 'swd')
        initial = read_scalar(out, inp, 0xe000edf0, 1)[0]
        write_scalar(out, inp, 0xe000edf0, [0xa05f0003])
        assert read_scalar(out, inp, 0xe000edf0, 1)[0] & (1 << 17), 'target did not halt'
        backup = read_scalar(out, inp, args.base, max(counts))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix('.backup.bin').write_bytes(b''.join(w.to_bytes(4, 'little') for w in backup))
        report['backup_transport'] = 'swd'
        setup(out, inp, args.speed, 'jtag')
        if args.idle is not None or args.half_delay:
            assert args.idle is None or 0 <= args.idle <= 15
            assert 0 <= args.half_delay <= 15
            script = args.output.with_suffix('.tcl').resolve()
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text('connect\ntargets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}\n'
                              + f'mwr -force 0x40010008 {1 | ((1 if args.idle is None else args.idle) << 4) | (args.half_delay << 13)}\n'
                              + 'disconnect\nexit\n')
            subprocess.run([sys.executable, str(Path(__file__).with_name('run_xsct.py')), str(script)], check=True)
        if args.mode is not None:
            xfer(out, inp, [0x89, args.mode])
        clock = xfer(out, inp, [0x80, 255])
        report['fclk_hz'] = int.from_bytes(clock[4:8], 'little')
        report['tck_hz'] = report['fclk_hz'] // (2 * (args.half_delay + 1))
        report['half_delay'] = args.half_delay
        report['timing'] = xfer(out, inp, [0x89, 255]).hex(' ')
        print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)
        for n in counts:
            for method in (('scalar', 'block', 'batch') if args.batch else ('scalar', 'block')):
                pattern = [(0x91910000 + i * 0x0101 + n * 0x10000) & 0xffffffff for i in range(n)]
                if args.pattern_seed is not None:
                    pattern = [rng.getrandbits(32) for _ in range(n)]
                # Poison SRAM so a missing write cannot retain correct data.
                write_scalar(out, inp, args.base, [w ^ 0xffffffff for w in pattern])
                if method == 'batch':
                    address(out, inp, args.base)
                    script = args.output.with_suffix('.tcl').resolve()
                    commands = [(5 << 24) | (n << 8) | 13, *pattern, 0x0300000e, 0]
                    script.write_text('connect\ntargets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}\n'
                        + ''.join(f'mwr -force {0x42000000+4*i:#x} {word:#x}\n' for i, word in enumerate(commands))
                        + 'mwr -force 0x40010030 0x1003\nafter 50\nputs [mrd -force 0x40010034]\ndisconnect\nexit\n')
                    batch_dump = subprocess.check_output([sys.executable, str(Path(__file__).with_name('run_xsct.py')),
                                                          str(script)], text=True)
                    print(batch_dump, flush=True)
                    assert '0000440A' in batch_dump.upper(), batch_dump
                else:
                    (write_scalar if method == 'scalar' else write_words)(out, inp, args.base, pattern)
                if method == 'block' and args.dump_command:
                    script = args.output.with_suffix('.tcl').resolve()
                    script.write_text('connect\ntargets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}\n'
                                      + f'puts [mrd -force 0x42000000 {n+1}]\n' + 'disconnect\nexit\n')
                    dump = subprocess.check_output([sys.executable, str(Path(__file__).with_name('run_xsct.py')),
                                                    str(script)], text=True)
                    print(dump, flush=True)
                    args.output.with_name(args.output.stem + f'_cmd_{n}.txt').write_text(dump)
                back = read_scalar(out, inp, args.base, n)
                bad = [{'index': i, 'got': hex(back[i]), 'want': hex(pattern[i])}
                       for i in range(n) if back[i] != pattern[i]]
                row = {'method': method, 'count': n, 'bad': bad}
                report['rows'].append(row)
                print(json.dumps(row), flush=True)
    finally:
        try:
            if backup is not None:
                setup(out, inp, 50000, 'swd')
                write_scalar(out, inp, args.base, backup)
                report['restore_match'] = read_scalar(out, inp, args.base, len(backup)) == backup
                assert report['restore_match'], 'SRAM restore failed'
        finally:
            if initial is not None:
                setup(out, inp, 50000, 'swd')
                write_scalar(out, inp, 0xe000edf0, [0xa05f0000 | (initial & 3)])
            xfer(out, inp, [2, 0])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    return int(any(row['bad'] for row in report['rows']))


if __name__ == '__main__':
    raise SystemExit(main())
