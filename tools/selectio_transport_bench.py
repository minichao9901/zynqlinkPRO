"""Measure the native USB path with a probe-DDR target at the exact SRAM request shape."""
import argparse
import hashlib
import json
from pathlib import Path

from selectio_native import native_connection
from selectio_pipeline_bench import measure_window


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial",default="12345678")
    parser.add_argument("--seconds",type=float,default=10)
    parser.add_argument("--schedule",choices=("sliding","grouped"),default="sliding")
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.seconds<=0:parser.error("positive window required")
    args.out.mkdir(parents=True,exist_ok=False)
    report={"schedule":args.schedule,"target":"private probe DDR","windows":[]}
    def save():
        (args.out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    seq=0
    try:
        with native_connection(args.serial) as dev:
            report["probe"]=dev.info()
            dev.sliding=args.schedule=="sliding"
            if dev.advertised_frame<16384:raise RuntimeError("probe lacks the private DDR transport benchmark")
            for frame in (4096,16384):
                dev.set_frame_size(frame)
                for n in sorted({1024,4032,dev.max_bulk}):
                    address=0x20008020
                    for depth in (1,4):
                        for direction in ("read","write","mixed"):
                            original=hashlib.shake_256(str(seq).encode()).digest(n)
                            dev.bulk_many([(address,n,original)],1,transport_only=True)
                            count,seconds,active,seq,last=measure_window(dev,direction,address,n,depth,args.seconds,
                                len(report["windows"]),seq,original,transport_only=True)
                            if dev.bulk_many([(address,n,None)],1,transport_only=True)!=[last]:
                                raise RuntimeError("final DDR payload differs")
                            report["windows"].append(dict(direction=direction,frame=frame,bytes=n,depth=depth,
                                requests=count,wall_s=seconds,active_s=active,MBps=n*count/seconds/1e6))
                            save()
        report["passed"]=True
    finally:save()


if __name__=="__main__":main()
