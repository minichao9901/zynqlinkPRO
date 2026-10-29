"""Load the RAM-only HPM5301 performance ELF, verify it and verify CPU clocks."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

from elftools.elf.elffile import ELFFile
import usb.util

from dap_pipeline_bench import le, open_dap, xfer
from riscv_target import RiscvTarget


def system_address(address):
    if address < 0x20000:
        return address + 0x1040000
    if 0x80000 <= address < 0xA0000:
        return address - 0x80000 + 0x1060000
    return address


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, default=Path('firmware/target/hpm5301_perf/build/output/demo.elf'))
    parser.add_argument('--output-dir', type=Path, default=Path('build/hpm5301_performance'))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = dict(elf=str(args.elf.resolve()), elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(), segments=[])
    dev, out, inp = open_dap()
    try:
        xfer(out, inp, [2, 2])
        xfer(out, inp, [0x11] + le(10000000))
        target = RiscvTarget(out, inp)
        target.active()
        target.halt()
        saved = {hex(r): target.register(r) for r in [0x7B0, 0x7B1] + list(range(0x1001, 0x1020))}
        (args.output_dir / 'original-core.json').write_text(json.dumps(saved, indent=2))
        with args.elf.open('rb') as stream:
            elf = ELFFile(stream)
            report['entry'] = elf.header.e_entry
            for segment in elf.iter_segments():
                if segment.header.p_type != 'PT_LOAD' or not segment.header.p_filesz:
                    continue
                at = system_address(segment.header.p_paddr)
                data = segment.data()
                data += b'\0' * (-len(data) % 4)
                backup = target.read(at, len(data))
                (args.output_dir / f'original-{at:08x}.bin').write_bytes(backup)
                print('LOAD', hex(at), len(data), flush=True)
                target.write(at, data)
                assert target.read(at, len(data)) == data, 'Target ELF verification failed'
                report['segments'].append(dict(address=hex(at), size=len(data), verified=True))
        target.register(0x7B1, report['entry'])
        target.resume()
        time.sleep(.3)
        values = struct.unpack('<18I', target.read(0xF0400000, 72))
        report.update(state=list(values), cpu_clock_register=hex(target.word(0xF4001800)),
                      cpu_Hz=values[1], ahb_Hz=values[2], mchtmr_Hz=values[3], measured_cpu_Hz=values[5])
        print(json.dumps(report, indent=2), flush=True)
        (args.output_dir / 'target-load.json').write_text(json.dumps(report, indent=2) + '\n')
        assert values[0] == 0x48504D50 and values[1] == 360000000
        assert 355000000 < values[5] < 365000000, 'CPU cycle/timer ratio incorrect'
    finally:
        usb.util.release_interface(dev, 0)
        usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
