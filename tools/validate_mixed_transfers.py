"""Exercise ordinary DAP_Transfer mixed/grouped requests against real SRAM.

No target reset or Flash programming. Back up and restore the first 1 KiB.
The API response order and data are checked, including AP posted-read drains.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

import usb.util
from dap_pipeline_bench import open_dap, setup, xfer, le

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--speed',type=int,default=50000)
ap.add_argument('--rounds',type=int,default=20)
ap.add_argument('--output',type=Path,required=True)
a=ap.parse_args()
d,o,i=open_dap()
backup=None;modified=False
result={'speed_kHz':a.speed,'rounds':a.rounds,'cases':0,'passed':False}
rng=random.Random(0x20261027)

def transfer(ops):
    assert 1<=len(ops)<=255
    payload=bytearray([5,0,len(ops)])
    for req,value in ops:
        payload.append(req)
        if not req&2:payload.extend(struct.pack('<I',value))
    r=xfer(o,i,payload)
    reads=sum(bool(req&2) for req,_ in ops)
    assert r[:3]==bytes([5,len(ops),1]) and len(r)==3+4*reads,r[:16].hex()
    return list(struct.unpack('<'+'I'*reads,r[3:]))

def memory(reading,data=None):
    transfer([(5,0x20000000)])
    p=bytes([6,0,0,1,15 if reading else 13])+(b'' if reading else data)
    r=xfer(o,i,p)
    assert r[:4]==bytes([6,0,1,1]) and len(r)==(1028 if reading else 4),r[:16].hex()
    return r[4:]

try:
    setup(o,i,a.speed);assert xfer(o,i,[4,1,64,0,0,0])==bytes([4,0])
    transfer([(5,0xe000edf0)])
    dhcsr=xfer(o,i,[6,0,1,0,15])
    assert dhcsr[:4]==bytes([6,1,0,1]) and struct.unpack('<I',dhcsr[4:])[0]&(1<<17),'Target must be halted'
    backup=memory(True)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.with_suffix('.backup.bin').write_bytes(backup)
    result['backup_sha256']=hashlib.sha256(backup).hexdigest()
    modified=True
    for _ in range(a.rounds):
        # Boundary counts straddle legacy/batch dispatch and the 255-op limit.
        for n in [7,8,16,254]:
            values=[rng.getrandbits(32) for _ in range(n)]
            assert transfer([(5,0x20000000)]+[(13,v) for v in values])==[]
            assert memory(True)[:n*4]==struct.pack('<'+'I'*n,*values)
            result['cases']+=1
        # Switching TAR interrupts a write run. Posted reads before another
        # write must be drained, and only requested read data may be returned.
        first=[rng.getrandbits(32) for _ in range(12)]
        second=[rng.getrandbits(32) for _ in range(12)]
        ops=([(5,0x20000000)]+[(13,v) for v in first]+
             [(5,0x20000000)]+[(15,0)]*12+
             [(5,0x20000040)]+[(13,v) for v in second]+
             [(5,0x20000040)]+[(15,0)]*12)
        assert transfer(ops)==first+second,'Mixed posted-read ordering mismatch'
        result['cases']+=1
    result['passed']=True
finally:
    try:
        if modified:
            setup(o,i,a.speed);assert xfer(o,i,[4,1,64,0,0,0])==bytes([4,0])
            memory(False,backup)
            result['restore_match']=memory(True)==backup
            assert result['restore_match'],'Original SRAM restore failed'
    finally:
        usb.util.release_interface(d,0);usb.util.dispose_resources(d)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
