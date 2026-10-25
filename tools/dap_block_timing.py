"""Raw DAP_TransferBlock timing with a proper DP power-up (CTRL/STAT + SELECT)."""
import json
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


def x(p):
    b = bytes(p)
    o.write(b, timeout=2000)
    if len(b) % 512 == 0:
        o.write(b"", timeout=2000)
    return bytes(i.read(PKT, timeout=2000))


x([0x02, 0x01])
x([0x11] + le(10_000_000))
x([0x13, 0x00])
x([0x12, 88] + [0x9E, 0xE7] + [0xFF] * 8 + [0x00])
x([0x04, 0x00, 0xE8, 0x03, 0x00, 0x00])
print("idcode", x([0x05, 0x00, 0x01, 0x02]).hex(" "))
print("select", x([0x05, 0x00, 0x01, 0x08] + le(0)).hex(" "))
print("csw", x([0x05, 0x00, 0x01, 0x01] + le(0x23000052)).hex(" "))
print("tar", x([0x05, 0x00, 0x01, 0x05] + le(0x20000000)).hex(" "))
r = x([0x06, 0x00, 4, 0x00, 0x0F])
print("block4", r.hex(" "))

# 20 blocks x 255 words = 20400 bytes stays inside the 20 KiB SRAM
def sweep(words, blocks):
    x([0x05, 0x00, 0x01, 0x05] + le(0x20000000))
    cmd = [0x06, 0x00, words & 0xFF, (words >> 8) & 0xFF, 0x0F]
    t0 = time.perf_counter()
    for _ in range(blocks):
        x(cmd)
    return time.perf_counter() - t0


for words, blocks in ((255, 20), (1000, 5), (500, 10)):
    total = 0
    for _ in range(5):
        total += sweep(words, blocks)
    payload = words * 4 * blocks * 5
    print(f"words={words} blocks={blocks} payload={payload} MBps={payload/total/1e6:.2f}")

usb.util.release_interface(dev, 0)
