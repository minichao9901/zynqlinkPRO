"""Qualify J7 SPI and serial reception through the two real F103 BYPASS cells."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

from dap_pipeline_bench import cmd, setup
from selectio_cli import connection
from selectio_native import native_connection


def install_bypass(tx,rx):
    setup(tx,rx,1000,"jtag")
    steps=[(1,6,0),(0,1,0),(1,2,0),(0,2,0),(0,8,255),(1,1,1),(1,1,0),(0,1,0),(1,1,0),(0,2,0)]
    packet=bytearray([0x14,len(steps)])
    for tms,n,data in steps:packet.extend((n|(tms<<6),data))
    if cmd(tx,rx,packet)!=b"\x14\0":raise RuntimeError("TAP setup rejected")
    pattern=bytes.fromhex("591f86cbe27a3504")
    reply=cmd(tx,rx,b"\x14\x01\x80"+pattern)
    got=int.from_bytes(reply[2:],"little")
    expected=(int.from_bytes(pattern,"little")<<2)&((1<<64)-1)
    if reply[:2]!=b"\x14\0" or got!=expected:
        raise RuntimeError(f"low-speed BYPASS differs: {got:016x} != {expected:016x}")
    cmd(tx,rx,b"\x14\x01\x02\x00")


def encode(data,manchester):
    bits=[0 if manchester else 1]*32
    if manchester:
        for first in range(0,len(data),8):
            bits.extend((1,0))
            for v in data[first:first+8]:
                for i in range(8):
                    b=(v>>i)&1
                    bits.extend((b,1-b))
            bits.extend([0]*8)
    else:
        for v in data:bits.extend([0,*((v>>i)&1 for i in range(8)),1])
    bits.extend([0 if manchester else 1]*32)
    while len(bits)%8:bits.append(bits[-1])
    return bytes(sum(bit<<(7-j) for j,bit in enumerate(bits[i:i+8])) for i in range(0,len(bits),8))


def captured(port,cfg,data):
    port.exchange(4,0,cfg)
    try:
        port.exchange(4,2,data)
        port.exchange(4,3)
        output=bytearray()
        while True:
            part=port.exchange(4,1)
            if not part:break
            output.extend(part)
        status=struct.unpack("<5I",port.exchange(4,4))
        return bytes(output),status
    finally:port.exchange(4,5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial",default="12345678")
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--seconds",type=float,default=10)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if not args.execute:
        print("Select the BYPASS instruction on both F103 TAPs, clock known symbols through TDI/TDO, then restore debug routing.")
        return
    args.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    def save():
        (args.out/"wire.json").write_text(json.dumps(rows,indent=2)+"\n")
    with connection(args.serial) as (tx,rx), native_connection(args.serial,tx.device) as port:
        port.info()
        try:
            for kind in ("spi","uart","manchester"):
                result=dict(kind=kind,points=[])
                rows.append(result)
                winner=None
                for tap in (0,8,16,24):
                    slots=(16,20,24,28,12,32,18,22,26,30,14,34,17,19,21,23,25,27) if kind=="spi" else (20,)
                    for slot in slots:
                        install_bypass(tx,rx)
                        sample=hashlib.shake_256(kind.encode()).digest(64)
                        codec={"spi":0,"uart":1,"manchester":2}[kind]
                        cfg=struct.pack("<BBBBIB",codec,2 if kind=="manchester" else 0,0,slot,100000000,tap)
                        wire=sample if kind=="spi" else encode(sample,kind=="manchester")
                        expected=(int.from_bytes(wire,"big")>>2).to_bytes(len(wire),"big") if kind=="spi" else sample
                        got,status=captured(port,cfg,wire)
                        ok=got==expected and status[:3]==(0,0,0)
                        point=dict(tap=tap,slot=slot,received=len(got),expected=len(expected),errors=status[2],overflow=status[1],
                                   prefix=got[:16].hex(),expected_prefix=expected[:16].hex(),passed=ok)
                        result["points"].append(point);save()
                        if ok: winner=cfg;break
                    if winner:break
                result["passed"]=winner is not None;save()
                if not winner:continue
                first=time.monotonic();cycles=0;total=0
                while time.monotonic()-first<args.seconds:
                    install_bypass(tx,rx)
                    sample=hashlib.shake_256(struct.pack("<I",cycles)).digest(2048 if kind=="spi" else 96)
                    wire=sample if kind=="spi" else encode(sample,kind=="manchester")
                    expect=(int.from_bytes(wire,"big")>>2).to_bytes(len(wire),"big") if kind=="spi" else sample
                    got,status=captured(port,winner,wire)
                    if got!=expect or any(status[:3]):
                        result.update(passed=False,error="confirmation mismatch",status=status,cycle=cycles);break
                    total+=len(got);cycles+=1
                result.update(confirmed_bytes=total,transactions=cycles,elapsed=time.monotonic()-first);save()
                print(kind,result["passed"],total,flush=True)
        finally:
            try:setup(tx,rx,1000,"swd")
            finally:cmd(tx,rx,[3])
    return 0 if all(r.get("passed") for r in rows) else 1


if __name__=="__main__":
    raise SystemExit(main())
