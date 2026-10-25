"""Verify a 1023-word block read (exercises the 1000+23 chunk split)."""
import struct
import time
from pathlib import Path

import libusb_package
import usb.core
import usb.util

PKT = 4096


def le(v):
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


dev = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                    backend=libusb_package.get_libusb1_backend())
intf = dev.get_active_configuration()[(0, 0)]
usb.util.claim_interface(dev, 0)
o = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
i = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)


def x(p, timeout=3000):
    b = bytes(p)
    o.write(b, timeout=timeout)
    if len(b) % 512 == 0:
        o.write(b"", timeout=timeout)
    return bytes(i.read(PKT, timeout=timeout))


x([0x02, 0x01]); x([0x11] + le(10_000_000)); x([0x13, 0]); x([0x12, 88] + [0x9E, 0xE7] + [0xFF] * 8 + [0x00])
x([0x04, 0, 0xE8, 3, 0, 0])
print("idcode", x([0x05, 0, 1, 0x02]).hex(" "))
print("select", x([0x05, 0, 1, 0x08] + le(0)).hex(" "))
print("csw", x([0x05, 0, 1, 0x01] + le(0x23000052)).hex(" "))
x([0x05, 0, 1, 0x05] + le(0x20000000))

t0 = time.perf_counter()
r = x([0x06, 0, 0xFF, 0x03, 0x0F])   # 1023 words
dt = (time.perf_counter() - t0) * 1e3
words = (len(r) - 4) // 4
pattern = Path("results/daplink/sram/pat_20480.bin").read_bytes()
expected = list(struct.unpack("<1023I", pattern[:4092]))
got = list(struct.unpack(f"<{words}I", r[4:4 + words * 4])) if words else []
mismatch = [k for k in range(min(len(expected), len(got))) if expected[k] != got[k]]
print(f"words={words} {dt:.2f} ms mismatches={len(mismatch)} first_bad={mismatch[:4]}")
print("first", r[4:12].hex(" "))
usb.util.release_interface(dev, 0)
