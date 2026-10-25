"""Raw CMSIS-DAP/WinUSB bulk endpoint benchmark for the composite bench."""
import argparse, json, time
from datetime import datetime, timezone
from pathlib import Path
import usb.core, usb.util, libusb_package

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--direction',choices=['in','out'],required=True); ap.add_argument('--seconds',type=float,default=3); ap.add_argument('--chunk',type=int,default=4096); ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    dev=usb.core.find(idVendor=0x0D28,idProduct=0x0204,backend=libusb_package.get_libusb1_backend())
    if dev is None: raise SystemExit('CMSIS-DAP device not found')
    cfg=dev.get_active_configuration(); intf=cfg[(0,0)]
    usb.util.claim_interface(dev,0)
    ep_out=usb.util.find_descriptor(intf,custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_OUT)
    ep_in=usb.util.find_descriptor(intf,custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_IN)
    payload=bytes(range(256))*((args.chunk+255)//256); payload=payload[:args.chunk]
    total=calls=0; t0=time.perf_counter()
    try:
        deadline=t0+args.seconds
        while time.perf_counter()<deadline:
            if args.direction=='out': n=ep_out.write(payload,timeout=2000)
            else: n=len(ep_in.read(args.chunk,timeout=2000))
            total+=n; calls+=1
    finally:
        try: usb.util.release_interface(dev,0)
        except Exception: pass
    elapsed=time.perf_counter()-t0
    result={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'direction':args.direction,'chunk':args.chunk,'bytes':total,'elapsed_seconds':elapsed,'MB_per_second':total/elapsed/1e6,'MiB_per_second':total/elapsed/1048576,'calls':calls,'endpoints':{'out':hex(ep_out.bEndpointAddress),'in':hex(ep_in.bEndpointAddress)}}
    print(json.dumps(result,indent=2)); args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__': main()
