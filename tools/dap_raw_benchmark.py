"""Measure raw CMSIS-DAP block USB round trips separately for read/write."""
import argparse
import json
import struct
import time
from pathlib import Path
import libusb_package
import usb.core
import usb.util

ap = argparse.ArgumentParser()
ap.add_argument('--speed', type=int, default=50000)
ap.add_argument('--words', type=int, default=1000)
ap.add_argument('--loops', type=int, default=100)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
d = usb.core.find(idVendor=0x0d28, idProduct=0x0204,
                  backend=libusb_package.get_libusb1_backend())
if d is None:
    raise RuntimeError('DAP not connected')
usb.util.claim_interface(d, 0)

def x(p):
    b = bytes(p)
    d.write(2, b, timeout=3000)
    if len(b) % 512 == 0:
        d.write(2, b'', timeout=3000)
    return bytes(d.read(0x81, 4096, timeout=3000))

def cmd(p):
    r = x(p)
    if not r or r[0] != p[0]:
        raise RuntimeError(r[:20].hex())
    return r

try:
    cmd([2, 1])
    cmd(bytes([0x11]) + struct.pack('<I', a.speed * 1000))
    cmd([0x12, 56] + [255] * 7)
    cmd([0x12, 16, 0x9e, 0xe7])
    cmd([0x12, 64] + [255] * 7 + [0])
    cmd([4, 0, 0xe8, 3, 0, 0])

    def wr(req, val):
        cmd(bytes([5, 0, 1, req]) + struct.pack('<I', val))

    def rd(req):
        r = cmd([5, 0, 1, req])
        if len(r) < 7:
            raise RuntimeError(f'reg read response {r.hex()}')
        return struct.unpack('<I', r[3:7])[0]

    wr(0, 0x1e)
    wr(8, 0)
    wr(4, 0x50000000)
    for _ in range(1000):
        if rd(6) & 0xa0000000 == 0xa0000000:
            break
    wr(1, 0x23000052)
    wr(5, 0x20000000)
    words = a.words
    payload = b''.join(struct.pack('<I', 0xA5000000 + i) for i in range(words))

    def block(req, data=b''):
        return cmd(bytes([6, 0, words & 255, words >> 8, req]) + data)

    block(13, payload)
    wr(5, 0x20000000)
    t = time.perf_counter()
    for _ in range(a.loops):
        r = block(15)
        if len(r) != 4 + words * 4:
            raise RuntimeError(f'read length {len(r)}')
    read_s = time.perf_counter() - t
    wr(5, 0x20000000)
    t = time.perf_counter()
    for _ in range(a.loops):
        block(13, payload)
    write_s = time.perf_counter() - t
    out = {'speed_kHz': a.speed, 'words': words, 'loops': a.loops,
           'read_MB_s': words * 4 * a.loops / read_s / 1e6,
           'write_MB_s': words * 4 * a.loops / write_s / 1e6,
           'read_s': read_s, 'write_s': write_s}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
finally:
    usb.util.release_interface(d, 0)
