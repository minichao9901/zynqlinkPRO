"""Compare zero/one idle on read-only AP register and SRAM transactions."""
import argparse
import json
from pathlib import Path
import struct

import usb.util
from dap_pipeline_bench import open_dap, setup, xfer, le

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--speed',type=int,default=50000)
ap.add_argument('--rounds',type=int,default=1000)
ap.add_argument('--output',type=Path,required=True)
a=ap.parse_args()
d,o,i=open_dap()
rows=[]
addresses=[0xe000edf0,0x40021000,0x40021004,0x20000000,0x20000004,0xe000ed00]

def write(req,value):
    r=xfer(o,i,[5,0,1,req]+le(value))
    if r!=bytes([5,1,1]):raise RuntimeError(f'write req={req:x} data={value:x} response={r.hex()}')

def read(address,packet):
    write(5,address)
    r=xfer(o,i,[6,0,1,0,15] if packet else [5,0,1,15])
    h=bytes([6,1,0,1]) if packet else bytes([5,1,1])
    if r[:len(h)]!=h or len(r)!=len(h)+4:
        raise RuntimeError(f'AP read address={address:x} packet={packet} response={r.hex()}')
    return struct.unpack('<I',r[len(h):])[0]

try:
    for idle in [1,0,1,0]:
        row={'speed_kHz':a.speed,'idle':idle,'passed':False}
        try:
            setup(o,i,a.speed)
            xfer(o,i,[4,1,0x40,0,0,0])
            write(0,0x1e)
            expected=[read(addr,True) for addr in addresses]
            xfer(o,i,[4,idle,0x40,0,0,0])
            cfg=xfer(o,i,[0x80,255])
            row['actual_idle']=(struct.unpack_from('<I',cfg,8)[0]>>4)&15
            assert row['actual_idle']==idle,'Firmware clamped zero idle; experimental build required'
            for n in range(a.rounds):
                address=addresses[n%len(addresses)]
                got=read(address,bool((n//len(addresses))%2))
                mask=0x0003000f if address==0xe000edf0 else 0xffffffff
                if (got&mask)!=(expected[n%len(addresses)]&mask):
                    raise RuntimeError(f'data address={address:x} got={got:x}')
            row.update(passed=True,transactions=a.rounds)
        except Exception as exc:
            row.update(error=str(exc),state=xfer(o,i,[0x87]).hex())
        rows.append(row);print(row,flush=True)
    if not all(r['passed'] for r in rows):raise RuntimeError('Idle regression failed')
finally:
    usb.util.release_interface(d,0);usb.util.dispose_resources(d)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(rows,indent=2))
