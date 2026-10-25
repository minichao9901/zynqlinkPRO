"""Sweep SWCLK using known IDCODE payloads and report the real PLL divisor."""
import argparse
import json
from pathlib import Path
import struct
import time

import libusb_package
import usb.core
import usb.util

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--speeds', type=int, nargs='+', default=[1000,10000,25000,50000,60000,75000,80000,82000,90000])
ap.add_argument('--phase', type=int, choices=[0,1], default=1)
ap.add_argument('--seconds', type=float, default=1)
ap.add_argument('--output', type=Path, required=True)
args = ap.parse_args()
d = usb.core.find(idVendor=0x0d28, idProduct=0x0204,
                  backend=libusb_package.get_libusb1_backend())
if d is None:
    raise RuntimeError('DAP not connected')
usb.util.claim_interface(d, 0)

def x(p):
    p = bytes(p)
    d.write(2, p, timeout=2000)
    if len(p) % 512 == 0:
        d.write(2, b'', timeout=2000)
    r = bytes(d.read(0x81, 4096, timeout=2000))
    if not r or r[0] != p[0]:
        raise RuntimeError(f'bad response {r[:16].hex()}')
    return r

def reset_line():
    x([0x12,56]+[255]*7)
    x([0x12,16,0x9e,0xe7])
    x([0x12,64]+[255]*7+[0])

rows=[]
try:
    for speed in args.speeds:
        row = {'requested_kHz':speed, 'phase':args.phase}
        try:
            x([2,1])
            if x(bytes([0x11])+struct.pack('<I',speed*1000)) != b'\x11\x00':
                raise RuntimeError('clock request rejected')
            diag=x([0x80,args.phase])
            if len(diag)!=12 or diag[1]!=0:
                raise RuntimeError(f'phase diagnostics failed {diag.hex()}')
            row['actual_SWCLK_Hz']=struct.unpack('<I',diag[4:8])[0]/2
            row['cfg']=hex(struct.unpack('<I',diag[8:12])[0])
            reset_line()
            x([4,0,64,0,0,0])
            expected=bytes([6,128,0,1])+struct.pack('<I',0x1ba01477)*128
            end=time.monotonic()+args.seconds
            n=0
            while time.monotonic()<end:
                r=x([6,0,128,0,2])
                if r!=expected:
                    raise RuntimeError(f'IDCODE mismatch {r[:32].hex()}')
                n+=128
            row.update(passed=True,verified_words=n)
        except Exception as e:
            row.update(passed=False,error=str(e))
        rows.append(row)
        print(json.dumps(row),flush=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(rows,indent=2))
finally:
    try:
        x(bytes([0x11])+struct.pack('<I',50000000))
        reset_line()
    finally:
        usb.util.release_interface(d,0)
