"""Explicit EP0 session recovery while IN responses are abandoned; no target writes."""
import argparse,json,time
from pathlib import Path
from dap_pipeline_bench import open_dap,xfer,send
import usb.util
import usb.core
import struct
def bounded_drain(inp):
 for n in range(64):
  try:inp.read(4096,timeout=80)
  except usb.core.USBTimeoutError:return n
 raise RuntimeError("64 stale responses after recovery")
def snapshot(dev):
 return struct.unpack("<8I",dev.ctrl_transfer(0xc0,0x5b,0x4441,0x5052,32,timeout=3000))
ap=argparse.ArgumentParser();ap.add_argument('--rounds',type=int,default=100);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
d,o,i=open_dap();rows=[]
try:
 bounded_drain(i)
 expected=xfer(o,i,[0,0xf0])
 assert expected[0]==0 and expected[1]==len(expected)-2 and expected[2]&1,expected.hex()
 for k in range(a.rounds):
  # Leave several old responses behind on the device, then begin a new
  # session. Vary the delay to cover reset-before-execution and in-flight IN.
  for j in range(8):send(o,[0,0xff])
  time.sleep((0,.0001,.001,.02)[k%4])
  before=snapshot(d)
  recovery=bytes(d.ctrl_transfer(0xc0,0x5a,0x4441,0x5052,4,timeout=3000))
  assert recovery==b'DAP\x00',recovery.hex()
  reset_state=snapshot(d)
  assert reset_state[:3]==(0,0,0),reset_state
  d.clear_halt(0x81);d.clear_halt(0x02)
  stale=bounded_drain(i)  # Discard bytes WinUSB may already have prefetched.
  r=xfer(o,i,[0,0xf0])
  if r!=expected:raise RuntimeError(f'reset={k} stale response {r.hex()}, expected {expected.hex()}')
  rows.append({'iteration':k,'before':before,'after_reset':reset_state,'after':snapshot(d),'host_prefetched_responses':stale,'new_session_caps':r.hex(),'pass':True})
  if k%10==0:print(f'recovery {k}: before={before}, drained={stale}',flush=True)
 print(f'PASS {a.rounds} EP0 recoveries with abandoned IN responses')
finally:
 usb.util.release_interface(d,0);usb.util.dispose_resources(d)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(rows,indent=2))
