"""Read the last 16 completed RTL SWD transfers, frozen on invalid ACK/parity."""
import argparse
import json
from pathlib import Path
import struct
import usb.util
from dap_pipeline_bench import open_dap,xfer

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--clear',action='store_true')
ap.add_argument('--output',type=Path)
a=ap.parse_args()
d,o,i=open_dap()
try:
 r=xfer(o,i,[0x88,int(a.clear)])
 assert len(r)==70 and r[:2]==b'\x88\x00',r.hex()
 control,*entries=struct.unpack('<17I',r[2:])
 count=(control>>4)&65535;head=control&15
 result={'frozen':bool(control>>31),'completed':count,'head':head,'history':[]}
 for n in range(min(count,16)):
  value=entries[(head-min(count,16)+n)%16]
  result['history'].append({'sequence':value>>16,'request':hex((value>>8)&255),'ACK':value&7,'parity_error':bool(value&8)})
 print(json.dumps(result,indent=2))
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2))
finally:usb.util.release_interface(d,0);usb.util.dispose_resources(d)
