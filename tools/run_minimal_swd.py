"""Run the independent GPIO SWD fixture; always restore an explicit probe pair."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--half-ns',default='500000,50000,5000,500')
 p.add_argument('--command',choices=['dpidr','ctrlstat'],default='dpidr')
 p.add_argument('--restore-bit',type=Path,required=True)
 p.add_argument('--restore-elf',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();work=ROOT/'build/minimal_swd';info=json.loads((work/'firmware.json').read_text())
 bit=work/'minimal_swd.bit';elf=work/'minimal_swd.elf';mailbox=info['mailbox_address']
 for path in [bit,elf,a.restore_bit,a.restore_elf]:assert path.is_file(),path
 sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
 report={'kind':'standalone PS/AXI GPIO SWD fixture','artifacts':{str(v.resolve()):sha(v) for v in [bit,elf]},
         'restore_pair':{str(v.resolve()):sha(v) for v in [a.restore_bit,a.restore_elf]},'rows':[]}
 ns_values=[int(v) for v in a.half_ns.split(',')];assert min(ns_values)>=100
 script=work/'run.tcl'
 body='''connect
targets -set -filter {name =~ "APU"}
rst -system
after 1000
source {INIT}
ps7_init
ps7_post_config
targets -set -filter {name =~ "xc7z020"}
fpga -f {BIT}
targets -set -filter {name =~ "ARM*#0"}
rst -processor
configparams force-mem-access 1
dow -chunksize 4096 {ELF}
con
after 200
targets -set -filter {name =~ "APU"}
if {[mrd -force -value MAILBOX] != 0x53574431} {error "Minimal firmware not ready"}
'''.replace('INIT',(ROOT/'prebuilt/ps7_init.tcl').as_posix()).replace('BIT',bit.as_posix()).replace('ELF',elf.as_posix()).replace('MAILBOX',hex(mailbox))
 for ns in ns_values:
  body+=f'''mwr -force {mailbox+8:#x} {ns}
mwr -force {mailbox+24:#x} 0
mwr -force {mailbox+4:#x} {1 if a.command=='dpidr' else 2}
set done 0
for {{set i 0}} {{$i < 300}} {{incr i}} {{
 after 10
 if {{[mrd -force -value {mailbox+24:#x}] == 1 && [mrd -force -value {mailbox+4:#x}] == 0}} {{set done 1;break}}
}}
if {{!$done}} {{error "Minimal SWD transfer timeout"}}
puts "BEGIN_ROW {ns}"
for {{set i 0}} {{$i < 96}} {{incr i}} {{puts [format "WORD %d %08X" $i [mrd -force -value [expr {{{mailbox} + 4*$i}}]]]}}
puts "END_ROW"
'''
 body+='disconnect\nexit\n';script.write_text(body)
 try:
  r=subprocess.run([sys.executable,str(ROOT/'tools/run_xsct.py'),str(script)],capture_output=True,text=True,errors='replace',timeout=120)
  (work/'run.log').write_text(r.stdout+r.stderr)
  assert r.returncode==0,r.stdout+r.stderr
  for ns,block in re.findall(r'BEGIN_ROW (\d+)\s+(.*?)END_ROW',r.stdout,re.S):
   words={int(i):int(v,16) for i,v in re.findall(r'WORD (\d+) ([0-9A-Fa-f]{8})',block)}
   assert len(words)==96 and words[0]==0x53574431 and words[6]==1,words
   parity=words[4].bit_count()&1
   row=dict(half_ns=int(ns),nominal_clock_hz=1e9/(2*int(ns)),ack=words[3],data=hex(words[4]),
            parity=words[5],parity_matches=parity==words[5],intended_rises=words[7],
            elapsed_ticks=words[80]+(words[81]<<32),timer_hz=words[82],
            bits=[{'index':i,'before_rise':words[8+2*i],'after_rise':words[9+2*i]} for i in range(36)])
   row['command']=a.command
   row['passed']=row['ack']==1 and words[4]==(0x1ba01477 if a.command=='dpidr' else 0xf0000000) and row['parity_matches']
   report['rows'].append(row)
   print(json.dumps({k:v for k,v in row.items() if k!='bits'}),flush=True)
 finally:
  restore=subprocess.run([sys.executable,str(ROOT/'tools/run_xsct.py'),str(ROOT/'tools/download_dap_fpga.tcl'),
                          str(a.restore_elf.resolve()),str(a.restore_bit.resolve())],capture_output=True,text=True,errors='replace',timeout=90)
  if restore.returncode:
   # A dead PL AXI slave can hold the PS debug AP busy. Reconfigure PL via
   # its independent FPGA TAP before retrying PS reset/download once.
   recovery=work/'restore_pl.tcl'
   recovery.write_text('connect\ntargets -set -filter {name =~ "xc7z020"}\nfpga -f {'
                       +a.restore_bit.resolve().as_posix()+'}\nafter 1000\ndisconnect\nexit\n')
   recovered=subprocess.run([sys.executable,str(ROOT/'tools/run_xsct.py'),str(recovery)],
                            capture_output=True,text=True,errors='replace',timeout=60)
   (work/'restore_pl.log').write_text(recovered.stdout+recovered.stderr)
   restore=subprocess.run([sys.executable,str(ROOT/'tools/run_xsct.py'),str(ROOT/'tools/download_dap_fpga.tcl'),
                           str(a.restore_elf.resolve()),str(a.restore_bit.resolve())],capture_output=True,text=True,errors='replace',timeout=90)
   report['pl_recovery_attempted']=True
  (work/'restore.log').write_text(restore.stdout+restore.stderr)
  report['probe_restored']=restore.returncode==0
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
  assert restore.returncode==0,restore.stdout+restore.stderr
 assert len(report['rows'])==len(ns_values)
 return int(any(not row['passed'] for row in report['rows']))


if __name__=='__main__':raise SystemExit(main())
