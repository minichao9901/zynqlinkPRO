"""Check Windows CDC at 100 Mbaud through the physical F103 two-TAP BYPASS chain."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

import serial
import serial.tools.list_ports
from dap_pipeline_bench import cmd,setup
from selectio_cli import connection
from selectio_native import native_connection
from selectio_wire_test import install_bypass


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial",default="12345678")
    ap.add_argument("--seconds",type=float,default=10)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--execute",action="store_true")
    args=ap.parse_args()
    if not args.execute:return print("Select both F103 BYPASS instructions; bind the CDC to real UART TX and TDO RX at 100 Mbaud.")
    args.out.mkdir(parents=True,exist_ok=False)
    matches=[p.device for p in serial.tools.list_ports.comports() if
             p.vid==0xd28 and p.pid==0x204 and p.serial_number==args.serial]
    if len(matches)!=1:raise RuntimeError("one matching J7 CDC port required")
    result=dict(port=matches[0],requested_baud=100000000,passed=False,bytes_each=0)
    with connection(args.serial) as (tx,rx),native_connection(args.serial,tx.device) as probe:
        probe.info()
        def status():return list(struct.unpack("<8I",probe.exchange(0,4)))
        try:
            install_bypass(tx,rx)
            probe.exchange(0,3,b"\x02")
            with serial.Serial(matches[0],100000000,timeout=2,write_timeout=2) as port:
                end=time.monotonic()+2
                while True:
                    values=status()
                    if values[:4]==[2,1,100000000,1]:break
                    if time.monotonic()>end:raise RuntimeError(f"Windows CDC line/ownership differs: {values}")
                    time.sleep(.01)
                result["line_coding"]=values
                port.reset_input_buffer()
                seq=0;digest=hashlib.sha256()
                started=time.perf_counter()
                while not seq or time.perf_counter()-started<args.seconds:
                    payload=hashlib.shake_256(struct.pack("<I",seq)).digest(4096)
                    if port.write(payload)!=len(payload):raise RuntimeError("short CDC write")
                    capture=port.read(len(payload))
                    if capture!=payload:
                        result.update(failing_block=seq,received=len(capture),expected_head=payload[:16].hex(),
                                      received_head=capture[:16].hex(),status=status())
                        raise RuntimeError("physical 100 Mbaud CDC return differs")
                    result["bytes_each"]+=len(capture);seq+=1;digest.update(capture)
                result.update(status=status(),sha256=digest.hexdigest(),elapsed=time.perf_counter()-started)
                if any(result["status"][5:]):raise RuntimeError("CDC error count or unconsumed input")
                result["passed"]=True
        finally:
            try:
                probe.exchange(0,3,b"\0")
                end=time.monotonic()+2
                while status()[1] and time.monotonic()<end:time.sleep(.01)
                if status()[1]:raise RuntimeError("CDC did not release the physical pins")
                setup(tx,rx,1000,"swd")
                cmd(tx,rx,[3])
            finally:(args.out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
