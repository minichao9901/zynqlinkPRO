"""Sustained RTT->CDC speed using a RAM-only blocking producer on F103CB.

The producer writes monotonic u32 words into an 8KiB RTT ring. Reader validates
all words, then producer is halted and the ring/CDC fully drained. Received bytes
must equal published words*4. All 20KiB RAM and architectural core registers are
backed up/restored; target clock and flash are not changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import time

import numpy as np
import serial
import serial.tools.list_ports
import usb.util

from dap_pipeline_bench import open_dap, setup
from probe_stream import Probe
from test_probe_board import Memory, stop

DHCSR, DCRSR, DCRDR = 0xe000edf0, 0xe000edf4, 0xe000edf8


def core_read(mem, index):
    mem.write_word(DCRSR, index)
    for _ in range(100):
        if mem.word(DHCSR) & (1 << 16):
            return mem.word(DCRDR)
    raise RuntimeError('DCRSR read timeout')


def core_write(mem, index, value):
    mem.write_word(DCRDR, value)
    mem.write_word(DCRSR, index | 0x10000)
    for _ in range(100):
        if mem.word(DHCSR) & (1 << 16):
            return
    raise RuntimeError('DCRSR write timeout')


class Reader(threading.Thread):
    def __init__(self, com):
        super().__init__(daemon=True)
        self.com = com
        self.quit = threading.Event()
        self.count = 0
        self.next_word = 0
        self.pending = b''
        self.error = None

    def run(self):
        try:
            while not self.quit.is_set():
                data = self.com.read(65536)
                self.count += len(data)
                data = self.pending+data
                n = len(data) & ~3
                if n:
                    a = np.frombuffer(data[:n], dtype='<u4')
                    assert int(a[0]) == self.next_word, (int(a[0]), self.next_word)
                    assert np.all(np.diff(a) == 1)
                    self.next_word = (int(a[-1])+1) & 0xffffffff
                self.pending = data[n:]
        except BaseException as exc:
            self.error = repr(exc)


def point(probe, mem, port, code, speed, chunk, seconds, repeat):
    mem.write_word(DHCSR, 0xa05f0003)
    mem.write(0x20000000, code)
    mem.write(0x20000200, struct.pack('<16sII6II', b'SEGGER RTT', 1, 0, 0, 0x20001000, 8192, 0, 0, 0, 0))
    core_write(mem, 16, 0x01000000)  # Clear inherited IT/condition state for the RAM entry.
    core_write(mem, 20, 1)  # privileged, interrupts masked, no fixture stack use
    core_write(mem, 15, 0x20000001)
    reader = None
    with serial.Serial(port, 115200, timeout=0.025) as com:
        com.reset_input_buffer()
        assert probe.action(0x31, 7, struct.pack('<IHBB', speed, chunk, 0, 1))[0] == 0
        assert probe.action(0x31, 1, struct.pack('<IIB', 0x20000200, 0x100, 0))[0] == 0
        reader = Reader(com)
        reader.start()
        try:
            mem.write_word(DHCSR, 0xa05f0001)
            time.sleep(0.3)
            t0 = time.perf_counter()
            rc, s0 = probe.action(0x31, 2)
            t0 = (t0+time.perf_counter())/2
            assert rc == 0 and s0[1] == 0x20000200 and s0[3]>0, (rc, s0)
            count0 = reader.count
            time.sleep(seconds)
            t1 = time.perf_counter()
            rc, s1 = probe.action(0x31, 2)
            t1 = (t1+time.perf_counter())/2
            count1 = reader.count
            assert rc == 0 and s1[5] == 0, (rc, s1)
            mem.write_word(DHCSR, 0xa05f0003)
            published_counter = mem.word(0x20000230)*4
            wr = mem.word(0x20000224)
            # Halt may land after publishing WrOff but before the stats store.
            in_flight_publish = (wr-(published_counter & 8191)) & 8191
            assert in_flight_publish in (0,4), (wr,published_counter)
            published = published_counter+in_flight_publish
            deadline = time.monotonic()+5
            while time.monotonic() < deadline:
                if reader.error:
                    raise RuntimeError(reader.error)
                if reader.count == published:
                    break
                time.sleep(0.02)
            assert probe.action(0x31, 0)[0] == 0
            time.sleep(0.05)
            reader.quit.set()
            reader.join(2)
            assert reader.error is None, reader.error
            assert reader.count == published and not reader.pending, (reader.count, published)
            return {'speed_hz': speed, 'chunk': chunk, 'repeat': repeat,
                    'window_s': t1-t0, 'host_bytes': count1-count0,
                    'host_MB_s': (count1-count0)/(t1-t0)/1e6,
                    'probe_bytes': (s1[3]-s0[3]) & 0xffffffff,
                    'probe_MB_s': ((s1[3]-s0[3]) & 0xffffffff)/(t1-t0)/1e6,
                    'session_bytes': published, 'sequence_exact': True,
                    'all_published_received': True, 'errors': s1[5], 's0': s0, 's1': s1}
        finally:
            mem.write_word(DHCSR, 0xa05f0003)
            probe.action(0x31, 0)
            reader.quit.set()
            reader.join(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seconds', type=float, default=3)
    ap.add_argument('--speeds', default='50000000,60000000')
    ap.add_argument('--chunks', default='128,256,512,1024')
    ap.add_argument('--repeats', type=int, default=1)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build = root/'build/rtt_ram'
    build.mkdir(parents=True, exist_ok=True)
    gcc = Path(shutil.which('arm-none-eabi-gcc'))
    objcopy = gcc.with_name('arm-none-eabi-objcopy.exe' if gcc.suffix == '.exe' else 'arm-none-eabi-objcopy')
    elf, binary = build/'producer.elf', build/'producer.bin'
    subprocess.run([str(gcc), '-mcpu=cortex-m3', '-mthumb', '-nostdlib',
                    '-Wl,-Ttext=0x20000000', '-Wl,-e,producer',
                    str(root/'firmware/target/probe_rtt_ram.S'), '-o', str(elf)], check=True)
    subprocess.run([str(objcopy), '-O', 'binary', str(elf), str(binary)], check=True)
    code = binary.read_bytes()
    assert len(code) < 512
    probe = Probe()
    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    backup, regs, initial = None, None, None
    report = {'kind': 'continuous RAM producer RTT->CDC', 'rows': []}
    try:
        stop(probe, dev)
        setup(out, inp, 50000)
        initial = mem.word(DHCSR)
        mem.write_word(DHCSR, 0xa05f0003)
        regs = {i: core_read(mem, i) for i in list(range(19))+[20]}
        backup = mem.read(0x20000000, 20480)
        args.output.with_suffix('.backup.bin').write_bytes(backup)
        report['backup_sha256'] = hashlib.sha256(backup).hexdigest()
        report['registers_before'] = regs
        report['RCC_before'] = [mem.word(0x40021000), mem.word(0x40021004)]
        port = next(p.device for p in serial.tools.list_ports.comports() if p.vid == 0xd28 and p.pid == 0x204)
        for speed in map(int, args.speeds.split(',')):
            for chunk in map(int, args.chunks.split(',')):
                for repeat in range(args.repeats):
                    row = point(probe, mem, port, code, speed, chunk, args.seconds, repeat)
                    report['rows'].append(row)
                    args.output.write_text(json.dumps(report, indent=2))
                    print(json.dumps({k:v for k,v in row.items() if k not in ('s0','s1')}), flush=True)
    finally:
        try:
            stop(probe, dev)
            setup(out, inp, 50000)
            mem.write_word(DHCSR, 0xa05f0003)
            if backup is not None:
                mem.write(0x20000000, backup)
                report['restore_match'] = mem.read(0x20000000, 20480) == backup
                assert report['restore_match']
            if regs is not None:
                for i, value in regs.items():
                    core_write(mem, i, value)
                after = {i: core_read(mem, i) for i in regs}
                report['registers_after'] = after
                report['registers_match'] = after == regs
                assert report['registers_match'], (regs, after)
            report['RCC_after'] = [mem.word(0x40021000), mem.word(0x40021004)]
            assert report.get('RCC_before', report['RCC_after']) == report['RCC_after']
            if initial is not None and not initial & (1 << 17):
                mem.write_word(DHCSR, 0xa05f0001)
        finally:
            args.output.write_text(json.dumps(report, indent=2))
            probe.close()
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)


if __name__ == '__main__':
    main()
