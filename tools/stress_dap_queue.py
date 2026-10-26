"""Stress legal 16-deep CMSIS-DAP queues, short/ZLP/full IN responses and sessions."""
import argparse,json,struct,time
from pathlib import Path
from dap_pipeline_bench import open_dap,setup,send,read_exact,xfer
import usb.util
ap=argparse.ArgumentParser();ap.add_argument('--rounds',type=int,default=100);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
rows=[]
for session in range(3):
 d,o,i=open_dap()
 try:
  setup(o,i,60000)
  for n in (1,127,128,255,256,1023):
   t=time.perf_counter()
   for k in range(a.rounds):
    requests=[]
    for j in range(8):
     requests.extend([(bytes([6,0,n&255,n>>8,15]),4+4*n),(bytes([5,0,1,2]),7)])
    for p,_ in requests:send(o,p)
    # Exercise DMA ownership while the host deliberately delays IN polling.
    if k%10==0:time.sleep(.002)
    for p,length in requests:
     r=read_exact(i,length)
     if len(r)!=length or r[0]!=p[0]:raise RuntimeError(f'session={session} n={n} k={k} response {r[:16].hex()} len={len(r)} expected={length}')
     if p[0]==6 and r[1:4]!=struct.pack('<HB',n,1):raise RuntimeError(f'block {r[:16].hex()}')
     if p[0]==5 and r[1:]!=bytes([1,1])+struct.pack('<I',0x1ba01477):raise RuntimeError(f'DPIDR {r.hex()}')
   row={'session':session,'words':n,'rounds':a.rounds,'seconds':time.perf_counter()-t,'pass':True};rows.append(row);print(row,flush=True)
 finally:
  usb.util.release_interface(d,0)
  usb.util.dispose_resources(d)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(rows,indent=2))

