"""Collect the diagnostic FCLK samples around an actual SWD ACK."""
from pathlib import Path
import argparse,json,struct
import usb.util
from dap_pipeline_bench import open_dap,setup,xfer,cmd,le
from test_swd_lowfreq_board import recover

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--speed',type=int,default=1000);p.add_argument('--phase',type=int,choices=[0,1],default=0);p.add_argument('--boundary',type=int,choices=[0,1]);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();dev,out,inp=open_dap()
 try:
  recover(dev,inp);cmd(out,inp,[0x84,0]);setup(out,inp,50000)
  cmd(out,inp,[0x11]+le(a.speed*1000));cmd(out,inp,[0x80,a.phase])
  if a.boundary is not None:cmd(out,inp,[0x89,a.boundary])
  cmd(out,inp,[0x13,0]);cmd(out,inp,[0x12,152]+[255]*8+[0x9e,0xe7]+[255]*8+[0]);cmd(out,inp,[4,1,64,0,0,0])
  cmd(out,inp,[0x88,2]);reply=xfer(out,inp,[5,0,1,2]);raw=cmd(out,inp,[0x88,0]);control=struct.unpack_from('<I',raw,2)[0]
  records=[]
  for i,w in enumerate(struct.unpack_from('<16I',raw,6)):
   row=dict(n=i,word=hex(w),direction=(w>>6)&1,host=(w>>5)&1,clock=(w>>4)&1,raw=(w>>3)&1,q1=(w>>2)&1,q2=(w>>1)&1);records.append(row);print(row)
  result=dict(speed_kHz=a.speed,phase=a.phase,reply=reply.hex(),control=hex(control),records=records)
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2));assert control==0x80000100
 finally:recover(dev,inp);setup(out,inp,50000);usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
if __name__=='__main__':main()
