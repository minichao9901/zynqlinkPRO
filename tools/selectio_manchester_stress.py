"""Long, single-session 100 Mbit/s Manchester test on the loaded J7 TDI pad."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

from dap_pipeline_bench import cmd,setup
from selectio_cli import connection
from selectio_native import native_connection
from selectio_wire_test import encode,install_bypass,pad_waveform


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678");ap.add_argument("--seconds",type=float,default=60)
    ap.add_argument("--out",required=True,type=Path);ap.add_argument("--execute",action="store_true")
    args=ap.parse_args()
    if not args.execute:return print("Drive fresh Manchester frames on loaded TDI and compare the decoded bytes in one active session.")
    args.out.mkdir(parents=True,exist_ok=False)
    digest=hashlib.sha256()
    report=dict(rate=100000000,source="J7 M15 physical pad with target load",bytes=0,blocks=0,passed=False)
    try:
        with connection(args.serial) as (tx,rx),native_connection(args.serial,tx.device) as port:
            info=port.info()
            if int(info["features"],16)&0x4000==0:raise RuntimeError("800 MS/s physical receiver required")
            install_bypass(tx,rx)
            active=False
            try:
                port.exchange(4,0,struct.pack("<BBBBIBB",2,2,0,21,100000000,0,1))
                active=True;start=time.perf_counter()
                while not report["blocks"] or time.perf_counter()-start<args.seconds:
                    data=hashlib.shake_256(struct.pack("<Q",report["blocks"])).digest(112)
                    waveform=pad_waveform(encode(data,True))
                    if len(waveform)>1536:raise RuntimeError("waveform exceeds raw RAM")
                    port.exchange(4,8,waveform)
                    got=bytearray(port.exchange(4,1))
                    deadline=time.perf_counter()+.25
                    while len(got)<len(data) and time.perf_counter()<deadline:
                        got.extend(port.exchange(4,1))
                    if got!=data:
                        report.update(failure_block=report["blocks"],expected=data.hex(),received=got.hex())
                        raise RuntimeError("Manchester byte comparison failed")
                    digest.update(got);report["blocks"]+=1;report["bytes"]+=len(data)
                report["elapsed"]=time.perf_counter()-start
                port.exchange(4,3)
                if port.exchange(4,1):raise RuntimeError("unexpected bytes after STOP")
                report["status"]=list(struct.unpack("<5I",port.exchange(4,4)))
                if any(report["status"][:3]):raise RuntimeError("FIFO count, overflow or framing errors")
                report.update(tpiu_frames=14*report["blocks"],sha256=digest.hexdigest(),passed=True)
            finally:
                if active:port.exchange(4,5)
                setup(tx,rx,1000,"swd");cmd(tx,rx,[3])
    finally:(args.out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))


if __name__=="__main__":main()
