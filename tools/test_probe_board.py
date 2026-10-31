"""F103 RAM-only acceptance for RTT/CDC and RTL HSS.

Halts the target if needed, backs up a 4KiB SRAM window, installs
temporary fixtures, verifies bytes/frames, and restores the complete SRAM window
and original run/halt state. Never resets the target or programs its flash.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import time

import serial
import serial.tools.list_ports
import usb.core
import usb.util

from dap_pipeline_bench import open_dap, setup, xfer, le
from probe_stream import Probe
from probe_build_info import provenance, swd_clock_details


class Memory:
    # AP TAR auto-increment wraps at 4 KiB on the STM32 AHB-AP (measured
    # 2026-10-29: a 1023-word read from page+0xC00 continues 1022,1023 then
    # 0,1,2 -- i.e. the 4 KiB page boundary, not the old 1 KiB assumption).
    # DAP_PACKET_SIZE is 4096 bytes on both directions: a read response carries
    # 4 header bytes (max 4092 payload = 1023 words), a write request carries
    # 5 header bytes (max 4088 payload = 1022 words).
    TAR_WRAP = 0x1000
    MAX_READ_BYTES = 4092
    MAX_WRITE_BYTES = 4088

    def __init__(self, out, inp):
        self.out, self.inp = out, inp

    def transfer(self, packet):
        return xfer(self.out, self.inp, packet)

    def address(self, addr):
        packet = [5, 0, 3, 8]+le(0)+[1]+le(0x23000052)+[5]+le(addr)
        assert self.transfer(packet) == b'\x05\x03\x01'

    def chunk(self, remaining, at, limit):
        return min(remaining, limit, self.TAR_WRAP-(at & (self.TAR_WRAP-1)))/4

    def read(self, addr, size):
        base = addr & ~3
        length = (size+(addr & 3)+3) & ~3
        data = b''
        while len(data) < length:
            at = base+len(data)
            count = int(self.chunk(length-len(data), at, self.MAX_READ_BYTES))
            self.address(at)
            reply = self.transfer([6, 0, count & 255, count >> 8, 15])
            assert reply[:4] == bytes([6, count & 255, count >> 8, 1]), reply.hex()
            assert len(reply) == 4+count*4
            data += reply[4:]
        return data[addr-base:addr-base+size]

    def write(self, addr, data):
        data = bytes(data)
        base = addr & ~3
        length = (len(data)+(addr & 3)+3) & ~3
        if base != addr or length != len(data):
            padded = bytearray(self.read(base, length))
            padded[addr-base:addr-base+len(data)] = data
            data = bytes(padded)
        offset = 0
        while offset < len(data):
            at = base+offset
            count = int(self.chunk(len(data)-offset, at, self.MAX_WRITE_BYTES))
            self.address(at)
            reply = self.transfer(bytes([6, 0, count & 255, count >> 8, 13])+data[offset:offset+count*4])
            assert reply == bytes([6, count & 255, count >> 8, 1]), reply.hex()
            offset += count*4

    def word(self, addr):
        return struct.unpack('<I', self.read(addr, 4))[0]

    def write_word(self, addr, value):
        self.write(addr, struct.pack('<I', value))


def drain_hss(dev, sink=None):
    count = 0
    while True:
        try:
            packet = bytes(dev.read(0x87, 512, timeout=20))
            if sink:
                sink(packet)
            count += 1
        except usb.core.USBTimeoutError:
            return count


def stop(probe, dev):
    for _ in range(20):
        rc, _ = probe.action(0x32, 0)
        drain_hss(dev)
        if rc == 0:
            break
        assert rc == -7, rc
    else:
        raise RuntimeError('HSS did not stop')
    assert probe.action(0x31, 0)[0] == 0


def test_rtt(probe, mem, base, port, speed_hz=50_000_000):
    ring = base+256
    control = struct.pack('<16sII6I', b'SEGGER RTT', 1, 0, 0, ring, 2048, 0, 0, 0)
    mem.write(base, control)
    diag = mem.transfer([0x80, 255])
    hz, cfg = struct.unpack_from('<II', diag, 4)
    expected_hz = int(swd_clock_details(hz, cfg)['SWCLK_Hz'])
    assert mem.transfer([3]) == b'\x03\x00'  # Force the probe to initialize SWD itself.
    rng = random.Random(20261027)
    total, wr = 0, 0
    start = time.monotonic()
    with serial.Serial(port, 115200, timeout=0.1) as com:
        com.reset_input_buffer()
        assert probe.action(0x31, 7, struct.pack('<IHBB', speed_hz, 1024, 0, 1))[0] == 0
        assert probe.action(0x31, 1, struct.pack('<IIB', base, 4096, 0))[0] == 0
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            rc,found=probe.action(0x31,2)
            assert rc in (0,-3), (rc,found)
            if found[1]==base:
                break
        else:
            raise RuntimeError('Probe-side cold SWD initialization/search failed')
        assert mem.transfer([2,1])==b'\x02\x01'
        assert mem.transfer([0x11]+le(speed_hz))==b'\x11\x00'
        for _ in range(3):
            for n in [1, 511, 512, 1023, 1024, 1537, 2047]:
                assert mem.word(base+40) == wr, 'Ring not drained before producer write'
                data = rng.randbytes(n)
                first = min(n, 2048-wr)
                mem.write(ring+wr, data[:first])
                if first < n:
                    mem.write(ring, data[first:])
                wr = (wr+n) % 2048
                mem.write_word(base+36, wr)
                got = b''
                deadline = time.monotonic()+3
                while len(got) < n and time.monotonic() < deadline:
                    got += com.read(n-len(got))
                assert got == data, f'CDC bytes mismatch size={n}: got={len(got)}'
                assert mem.word(base+40) == wr
                total += n
        rc, words = probe.action(0x31, 2)
        assert rc == 0 and words[3] == total and words[5] == 0, (rc, words)
        assert words[11] >> 24 == expected_hz // 1_000_000, words
        assert probe.action(0x31, 0)[0] == 0
    return {'bytes': total, 'rounds': 21, 'byte_exact': True, 'cold_probe_initialization': True, 'status': words,
            'reported_SWCLK_MHz': words[11] >> 24,
            'elapsed_including_host_producer_s': time.monotonic()-start}


def test_hss(probe, mem, dev, base, version, wide, seconds, speed_hz=50_000_000):
    fixture = random.Random(0x485353).randbytes(4096)
    mem.write(base, fixture)
    variables = [(base+0x100, 4, 4)]
    if wide:
        variables = [(base+0x101, 8, 7), (base+0x3ff, 4, 4), (base+0x300, 1, 0),
                     (base+0x304, 2, 2), (base+0x580, 8, 7), (base+0x021, 1, 0),
                     (base+0x7fd, 4, 5), (base+0x6ff, 2, 3)]
    expected = b''.join(fixture[a-base:a-base+n] for a, n, _ in sorted(variables))
    period = 2400 if version == 2 else 100
    assert probe.action(0x32, 3, struct.pack('<I', speed_hz))[0] == 0
    cfg = struct.pack('<IBB', period, 0, len(variables))
    cfg += b''.join(struct.pack('<IBB', *v) for v in variables)
    assert probe.action(0x32, 10 if version == 2 else 7, cfg)[0] == 0
    drain_hss(dev)
    # Cache a host TAR before starting the autonomous reader. The later raw
    # DRW reads deliberately do not rewrite TAR, testing real AP restoration.
    mem.address(base+0x900)
    diag = mem.transfer([0x80, 255])
    hz, cfg = struct.unpack_from('<II', diag, 4)
    expected_hz = int(swd_clock_details(hz, cfg)['SWCLK_Hz'])
    assert probe.action(0x32, 1)[0] == 0
    rc, active = probe.action(0x32, 2)
    assert rc == 0 and active[1] == expected_hz, (expected_hz, active)
    count, packets, definitions, last_seq = 0, 0, 0, None

    def accept(packet):
        nonlocal count, packets, definitions, last_seq
        assert len(packet) == 512 and packet[:2] == b'SJ' and packet[2] == version
        _, _, kind, seq, stamp, n, aux = struct.unpack_from('<HBBIIHH', packet)
        if last_seq is not None:
            assert seq == (last_seq+1) & 0xffffffff, (last_seq, seq)
        last_seq = seq
        packets += 1
        if kind == 1:
            definitions += 1
            assert aux == len(variables) and struct.unpack_from('<I', packet, 20)[0] == period
        elif kind == 2:
            assert aux == n*len(expected) and n > 0
            assert packet[16:16+aux] == expected*n, (version, wide, seq, stamp)
            count += n

    try:
        for i in range(8):
            reply = mem.transfer([6, 0, 1, 0, 15])
            assert reply[:4] == b'\x06\x01\x00\x01'
            assert reply[4:] == fixture[0x900+4*i:0x904+4*i], 'DAP TAR/CSW context was not restored'
        # Intentional host pause must fill queues and count skipped samples.
        # PL now adds eight packet banks ahead of the eight DDR USB slots.
        # At 10 kHz/u32 they hold about 0.2 s; exceed that capacity explicitly.
        time.sleep(0.3)
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            accept(bytes(dev.read(0x87, 512, timeout=1000)))
        rc, metrics = probe.action(0x32, 11)
        assert rc == 0 and metrics[0] == 0x31535348 and metrics[6] == 0, (rc, metrics)
        assert metrics[4] > 0, 'Backpressure did not count skipped samples'
        for _ in range(20):
            rc, _ = probe.action(0x32, 0)
            drain_hss(dev, accept)
            if rc == 0:
                break
            assert rc == -7
        else:
            raise RuntimeError('HSS stop did not complete')
        rc, final = probe.action(0x32, 11)
        assert rc == 0 and count == final[3], (count, final)
        assert definitions == 1 and count > 0
        return {'version': version, 'variables': len(variables), 'samples': count,
                'actual_SWCLK_Hz': active[1],
                'packets': packets, 'byte_exact': True, 'DAP_context_reads': 8,
                'metrics': final, 'backpressure_skipped': final[4]}
    finally:
        probe.action(0x32, 0)
        drain_hss(dev)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--services', choices=['rtt', 'hss', 'both'], default='both')
    ap.add_argument('--port')
    ap.add_argument('--seconds', type=float, default=0.25)
    ap.add_argument('--speed-hz', type=int, default=50_000_000)
    ap.add_argument('--ram-base', type=lambda s: int(s, 0),
                    help='4KiB fixture window; defaults to end of F103CB/xE SRAM')
    ap.add_argument('--bit', type=Path)
    ap.add_argument('--elf', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    probe = Probe()
    dev, out, inp = open_dap()
    mem = Memory(out, inp)
    report = {'speed_hz': args.speed_hz,
              'artifacts': provenance(args.bit, args.elf)}
    backup, initial_dhcsr = None, None
    try:
        stop(probe, dev)
        report['IDCODE'] = setup(out, inp, args.speed_hz//1000).hex()
        # DAP transport selection and the autonomous service preference are
        # separate. A preceding JTAG client may have left the latter at JTAG;
        # this test deliberately disconnects DAP to exercise cold SWD startup.
        assert probe.action(0x31, 12, bytes([1]))[0] == 0
        report['service_transport'] = 'swd'
        device = mem.word(0xe0042000) & 0xfff
        report['target'] = 'STM32F103xE' if device == 0x414 else 'STM32F103CB-compatible'
        report['device_id'] = hex(device)
        base = args.ram_base if args.ram_base is not None else (0x2000f000 if device == 0x414 else 0x20004000)
        report['RAM_base'] = hex(base)
        diagnostic = xfer(out, inp, [0x80, 255])
        hz, cfg = struct.unpack_from('<II', diagnostic, 4)
        report['waveform'] = dict(FCLK_Hz=hz, cfg=hex(cfg), **swd_clock_details(hz, cfg))
        initial_dhcsr = mem.word(0xe000edf0)
        if not initial_dhcsr & (1 << 17):
            mem.write_word(0xe000edf0, 0xa05f0003)
        assert mem.word(0xe000edf0) & (1 << 17)
        backup = mem.read(base, 4096)
        args.output.with_suffix('.backup.bin').write_bytes(backup)
        report['backup_sha256'] = hashlib.sha256(backup).hexdigest()
        if args.services in ('rtt', 'both'):
            port = args.port or next(p.device for p in serial.tools.list_ports.comports()
                                     if p.vid == 0x0d28 and p.pid == 0x0204)
            # Exercise SET_CONFIGURATION lifecycle and clear probe-side link cache.
            dev.ctrl_transfer(0,9,1,0,None,timeout=3000)
            time.sleep(0.02)
            report['rtt'] = test_rtt(probe, mem, base, port, args.speed_hz)
        if args.services in ('hss', 'both'):
            report['hss'] = [test_hss(probe, mem, dev, base, version, wide, args.seconds, args.speed_hz)
                             for version, wide in [(1, False), (2, False), (2, True)]]
    finally:
        try:
            stop(probe, dev)
            if backup is not None:
                setup(out, inp, 50000)
                mem.write(base, backup)
                restored = mem.read(base, 4096)
                report['restore_sha256'] = hashlib.sha256(restored).hexdigest()
                report['restore_match'] = restored == backup
                assert report['restore_match'], 'Original target SRAM was not restored'
            if initial_dhcsr is not None and not initial_dhcsr & (1 << 17):
                mem.write_word(0xe000edf0, 0xa05f0001)
        finally:
            args.output.write_text(json.dumps(report, indent=2))
            probe.close()
            usb.util.release_interface(dev, 0)
            usb.util.dispose_resources(dev)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
