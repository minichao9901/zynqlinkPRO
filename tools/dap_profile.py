"""Control cached aggregate profiling; no per-MMIO trace instrumentation."""
import argparse
import json
from pathlib import Path
import struct
import libusb_package
import usb.core
import usb.util

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('action',choices=['start','stop','read'])
ap.add_argument('--output',type=Path)
args=ap.parse_args()
d=usb.core.find(idVendor=0x0d28,idProduct=0x0204,
               backend=libusb_package.get_libusb1_backend())
if d is None:raise RuntimeError('DAP not connected')
usb.util.claim_interface(d,0)
try:
    d.write(2,bytes([0x81,{'start':1,'stop':0,'read':2}[args.action]]),timeout=3000)
    r=bytes(d.read(0x81,4096,timeout=3000))
    if len(r)!=82 or r[:2]!=b'\x81\x00':raise RuntimeError(r.hex())
    values=struct.unpack('<14I3Q',r[2:])
    names=['timer_Hz','xfer_batch_simple','xfer_legacy_multi','xfer_legacy_flags',
           'xfer_block_batch','xfer_block_read_words','xfer_block_write_words',
           'xfer_block_legacy_flags','xfer_block_legacy_depth','batch_calls',
           'upload_calls','download_calls','upload_bytes','download_bytes',
           'batch_ticks','upload_ticks','download_ticks']
    out=dict(zip(names,values))
    for prefix in ['batch','upload','download']:
        out[prefix+'_ms']=out[prefix+'_ticks']/out['timer_Hz']*1000
        out[prefix+'_mean_us']=out[prefix+'_ms']*1000/max(1,out[prefix+'_calls'])
    print(json.dumps(out,indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(out,indent=2))
finally:usb.util.release_interface(d,0)
