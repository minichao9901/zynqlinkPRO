"""Verify or restore the target RAM/register snapshot captured before board tests."""
from pathlib import Path
import argparse,json,hashlib
import usb.util
from dap_pipeline_bench import open_dap,setup
from test_probe_board import Memory
from benchmark_rtt_forward import core_read,core_write,DHCSR

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True);p.add_argument('--ram',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--restore',action='store_true');a=p.parse_args()
 original=json.loads(a.state.read_text());backup=a.ram.read_bytes();assert hashlib.sha256(backup).hexdigest()==original['RAM_sha256']
 dev,out,inp=open_dap();mem=Memory(out,inp)
 try:
  setup(out,inp,50000);mem.write_word(DHCSR,0xa05f0003)
  if a.restore:
   mem.write(0x20000000,backup)
   for i,v in original['registers'].items():core_write(mem,int(i),v)
  regs={str(i):core_read(mem,i) for i in list(range(19))+[20]}
  data=mem.read(0x20000000,len(backup));rcc=[hex(mem.word(0x40021000)),hex(mem.word(0x40021004))]
  result=dict(RAM_match=data==backup,registers_match=regs==original['registers'],RCC_match=rcc==original['RCC'],RCC=rcc,registers=regs,RAM_sha256=hashlib.sha256(data).hexdigest(),restore_requested=a.restore)
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2));print(json.dumps(result))
  assert result['RAM_match'] and result['registers_match'] and result['RCC_match']
  if a.restore and not int(original['DHCSR_before'],16)&(1<<17):mem.write_word(DHCSR,0xa05f0001)
 finally:usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
if __name__=='__main__':main()
