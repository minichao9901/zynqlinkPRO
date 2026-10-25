"""Validate repeat/chunk boundaries, USB ZLP sizes and random SRAM payloads."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import time
import libusb_package
import usb.core
import usb.util

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output', type=Path, default=Path('results/optimization/dma_raw_validation.json'))
ap.add_argument('--idle',type=int,choices=[0,1],default=0)
ap.add_argument('--speed',type=int,default=50000,help='SWCLK kHz')
args = ap.parse_args()
d = usb.core.find(idVendor=0x0d28,idProduct=0x0204,backend=libusb_package.get_libusb1_backend())
if d is None: raise RuntimeError('DAP not connected')
itf = d.get_active_configuration()[(0,0)]
usb.util.claim_interface(d,0)
eo = usb.util.find_descriptor(itf,bEndpointAddress=0x02)
ei = usb.util.find_descriptor(itf,bEndpointAddress=0x81)
def x(p):
    b=bytes(p); eo.write(b,timeout=3000)
    if len(b)%512==0:eo.write(b'',timeout=3000)
    r=bytes(ei.read(4096,timeout=3000))
    if not r or r[0]!=b[0]:raise RuntimeError(f'bad response {r[:16].hex()} for {b[:16].hex()}')
    return r
def wr(req,val):
    r=x(bytes([5,0,1,req])+struct.pack('<I',val))
    if r[1:3]!=b'\x01\x01':raise RuntimeError(f'register write failed: {r.hex()}')
def rd(req):
    r=x([5,0,1,req])
    if r[1:3]!=b'\x01\x01':raise RuntimeError(f'register read failed: {r.hex()}')
    return struct.unpack('<I',r[3:7])[0]
def tar():wr(5,0x20000000)
def block(req,n,data=b''):
    r=x(bytes([6,0,n&255,n>>8,req])+data)
    if len(r)<4 or r[1:4]!=struct.pack('<HB',n,1):raise RuntimeError(f'block failed: {r[:16].hex()} n={n}')
    if len(r)!=(4+4*n if req&2 else 4):raise RuntimeError(f'length mismatch {len(r)} n={n}')
    return r[4:]
rows=[]
try:
    x([2,1]); x(bytes([0x11])+struct.pack('<I',args.speed*1000));x([0x13,0])
    x([0x12,56]+[255]*7)
    x([0x12,16,0x9e,0xe7])
    x([0x12,64]+[255]*7+[0])
    x([4,args.idle,0xe8,3,0,0])
    print('DPIDR',hex(rd(2)),flush=True)
    wr(0,0x1e);wr(8,0);wr(4,0x50000000)
    for _ in range(100):
        if rd(6)&0xa0000000==0xa0000000:break
        time.sleep(.001)
    else:raise RuntimeError('DP power-up failed')
    wr(1,0x23000052)
    rng=random.Random(0x20261025)
    for n in (1,2,127,128,255,256,500,770,1000,1001,1022):
        payload=rng.randbytes(n*4)
        tar();block(13,n,payload);tar();got=block(15,n)
        if got!=payload:raise RuntimeError(f'SRAM mismatch at {n} words')
        row={'words':n,'sha256':hashlib.sha256(payload).hexdigest(),'match':True}
        rows.append(row);print(row,flush=True)
    # Read response is exactly 4096B, followed by another command to expose ZLP leakage.
    tar();data=block(15,1023)
    if data[:len(payload)]!=payload:raise RuntimeError('1023-word read corrupted preceding write')
    rd(2)
    rows.append({'words':1023,'read_length':len(data),'following_command_ok':True})
    # Mixed 0x05 stream: TAR writes, AP posted reads, and intervening DP reads.
    ops=[bytes([8])+struct.pack('<I',0), bytes([1])+struct.pack('<I',0x23000052),
         bytes([5])+struct.pack('<I',0x20000000),bytes([15]),bytes([15]),bytes([2]),
         bytes([5])+struct.pack('<I',0x20000010),bytes([15]),bytes([15]),bytes([6])]
    r=x(bytes([5,0,len(ops)])+b''.join(ops))
    if r[1:3]!=bytes([len(ops),1]) or len(r)!=27:raise RuntimeError(f'mixed 0x05 failed: {r.hex()}')
    got=list(struct.unpack('<6I',r[3:]))
    expected=[int.from_bytes(payload[o:o+4],'little') for o in (0,4)]
    expected += [0x1ba01477]
    expected += [int.from_bytes(payload[o:o+4],'little') for o in (16,20)]
    if got[:5]!=expected or got[5]&0xa0000000!=0xa0000000:raise RuntimeError(f'mixed read map failed: {got}')
    rows.append({'mixed_05_operations':len(ops),'posted_read_mapping_match':True})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(rows,indent=2))
    print('ALL RAW DMA BOUNDARY CHECKS PASSED')
finally:
    usb.util.release_interface(d,0)
