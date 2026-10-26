"""Read low-overhead, opt-in per-stage metrics (vendor 0x81/0x86)."""
import argparse,json,struct
from pathlib import Path
from dap_pipeline_bench import open_dap,xfer
NAMES=['execute_05_or_control','execute_06_read','execute_06_write','packet_read','packet_write','dma_upload','dma_download','response_copy','request_queue_wait','usb_in_submit_to_complete','usb_in_submit']
ap=argparse.ArgumentParser();ap.add_argument('action',choices=['start','stop','read']);ap.add_argument('--output',type=Path);a=ap.parse_args()
d,o,i=open_dap()
try:
 import usb.util
 r=xfer(o,i,[0x81,{'start':1,'stop':0,'read':2}[a.action]])
 if a.action=='start':print('profiling enabled');raise SystemExit()
 r=xfer(o,i,[0x86]);assert r[:4]==bytes([0x86,0,1,len(NAMES)]),r.hex()
 hz=struct.unpack_from('<I',r,4)[0];result={'timer_Hz':hz,'stages':{}}
 for k,name in enumerate(NAMES):
  ticks,calls,nbytes=struct.unpack_from('<QII',r,8+16*k)
  result['stages'][name]={'calls':calls,'bytes':nbytes,'total_ms':ticks/hz*1000,'mean_us':ticks/hz*1e6/calls if calls else 0}
 print(json.dumps(result,indent=2))
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2))
finally:usb.util.release_interface(d,0)
