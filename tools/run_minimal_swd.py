"""Run the independent GPIO SWD fixture; always restore an explicit probe pair."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--half-ns',default='500000,50000,5000,500')
 # The fixture resets the SW-DP before every request. DPIDR must be the
 # first successful read out of reset; a raw CTRL/STAT request is invalid.
 p.add_argument('--command',choices=['dpidr'],default='dpidr')
 p.add_argument('--pulse-mode',choices=['direct','short','both'],default='direct')
 p.add_argument('--fixture',choices=['gpio','main'],default='gpio')
 p.add_argument('--fclk-hz',type=int,choices=[50000000,100000000],default=100000000)
 p.add_argument('--short-clock-cycles',type=float,choices=[0.5,1.0],default=0.5,
                help='0.5 for the ODDR fixture; 1 for the archived single-FF short-pulse fixture')
 p.add_argument('--bit',type=Path,help='Optional IO-only variant of the same minimal design')
 p.add_argument('--restore-bit',type=Path,required=True)
 p.add_argument('--restore-elf',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 if a.fixture=='main' and (not a.bit or a.pulse_mode!='direct'):
  p.error('The main CSR fixture requires --bit and --pulse-mode direct')
 work=ROOT/('build/minimal_swd_main' if a.fixture=='main' else 'build/minimal_swd')
 info=json.loads((work/'firmware.json').read_text());assert info.get('fixture','gpio')==a.fixture
 bit=a.bit.resolve() if a.bit else work/'minimal_swd.bit';elf=work/'minimal_swd.elf';mailbox=info['mailbox_address']
 for path in [bit,elf,a.restore_bit,a.restore_elf]:assert path.is_file(),path
 sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
 report={'kind':'minimal PS SWD driver','fixture':a.fixture,'requested_fclk_hz':a.fclk_hz,'artifacts':{str(v.resolve()):sha(v) for v in [bit,elf]},
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
# BD constraints do not program PS clock dividers. Set FCLK explicitly.
set pll [mrd -force -value 0xf8000108]
set divisor [expr {int(round(33333333.0*(($pll>>12)&127)/FCLK_REQUEST))}]
if {$divisor<1 || $divisor>63} {error "Invalid fixture FCLK divisor"}
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000170 [expr {1 | (1<<8) | ($divisor<<20)}]
mwr -force 0xf8000004 0x767b
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
'''.replace('INIT',(ROOT/'prebuilt/ps7_init.tcl').as_posix()).replace('BIT',bit.as_posix()).replace('ELF',elf.as_posix()).replace('MAILBOX',hex(mailbox)).replace('FCLK_REQUEST',str(a.fclk_hz))
 modes=['direct','short','direct'] if a.pulse_mode=='both' else [a.pulse_mode]
 for mode,ns in [(mode,ns) for mode in modes for ns in ns_values]:
  body+=f'''mwr -force {mailbox+8:#x} {ns}
mwr -force {mailbox+24:#x} 0
mwr -force {mailbox+4:#x} {(1 if a.command=='dpidr' else 2) | (4 if mode=='short' else 0)}
set done 0
for {{set i 0}} {{$i < 300}} {{incr i}} {{
 after 10
 if {{[mrd -force -value {mailbox+24:#x}] == 1 && [mrd -force -value {mailbox+4:#x}] == 0}} {{set done 1;break}}
}}
if {{!$done}} {{error "Minimal SWD transfer timeout"}}
puts "BEGIN_ROW {ns} {mode}"
for {{set i 0}} {{$i < 96}} {{incr i}} {{puts [format "WORD %d %08X" $i [mrd -force -value [expr {{{mailbox} + 4*$i}}]]]}}
puts "END_ROW"
'''
 body+='disconnect\nexit\n';script.write_text(body)
 try:
  r=subprocess.run([sys.executable,str(ROOT/'tools/run_xsct.py'),str(script)],capture_output=True,text=True,errors='replace',timeout=120)
  (work/'run.log').write_text(r.stdout+r.stderr)
  assert r.returncode==0,r.stdout+r.stderr
  for ns,mode,block in re.findall(r'BEGIN_ROW (\d+) (direct|short)\s+(.*?)END_ROW',r.stdout,re.S):
   words={int(i):int(v,16) for i,v in re.findall(r'WORD (\d+) ([0-9A-Fa-f]{8})',block)}
   assert len(words)==96 and words[0]==0x53574431 and words[6]==1,words
   parity=words[4].bit_count()&1
   row=dict(half_ns=int(ns),pulse_mode=mode,nominal_clock_hz=1e9/(2*int(ns)),ack=words[3],data=hex(words[4]),
            parity=words[5],parity_matches=parity==words[5],intended_rises=words[7],
            elapsed_ticks=words[80]+(words[81]<<32),timer_hz=words[82],
            bits=[{'index':i,'before_rise':words[8+2*i],'after_rise':words[9+2*i]} for i in range(36)])
   row['command']=a.command
   row['PS_clock_registers']={name:hex(words[index]) for name,index in [('FCLK0_CTRL',92),('IO_PLL_CTRL',93),('ARM_PLL_CTRL',94)]}
   ctrl=words[92];source=(ctrl>>4)&3
   pll=words[93] if source in (0,1) else words[94] if source==2 else 0
   assert pll and not pll&0x10,'Fixture PLL bypass/source unsupported'
   row['actual_fclk_hz']=33333333*((pll>>12)&127)/(((ctrl>>8)&63)*((ctrl>>20)&63))
   if mode=='short':row['intended_high_pulse_ns']=1e9*a.short_clock_cycles/row['actual_fclk_hz']
   row['pad_observer']={label:dict(raw=hex(words[index]),pad_rises=(words[index]>>4)&255,
       expected_rises=words[index+1],fall_while_high=bool(words[index]&4),rise_while_low=bool(words[index]&8))
       for label,index in [('constant_high_preamble',83),('before_receive',85),('after_receive',87),('final',89)]}
   if a.fixture=='main' and words[91]>>16!=0x5343:row['pad_observer']=None
   row['passed']=row['ack']==1 and words[4]==0x1ba01477 and row['parity_matches']
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
 assert len(report['rows'])==len(ns_values)*len(modes)
 return int(any(not row['passed'] for row in report['rows']))


if __name__=='__main__':raise SystemExit(main())
