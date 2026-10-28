"""Packet/batch wire regressions, including zero idle and error cancellation."""
from pathlib import Path
import subprocess,json,re,hashlib
root=Path(__file__).resolve().parents[1];out=root/'build/swd_rx_wire_final';out.mkdir(exist_ok=True)
(out/'sources.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*(root/'fpga/rtl').glob('*.v'),*(root/'fpga/sim').glob('*.sv')]},indent=2))
rows=[]
for rx,half,tco in [(0,5,16),(1,10,1),(1,10,16),(1,25,16),(1,50,32)]:
 for idle in [0,1,2]:
  top='tb_packet_wire_budget';name=f'rx{rx}_half{half}_ret{tco}_idle{idle}';exe=out/(name+'.vvp')
  cmd=['iverilog','-g2012','-s',top,'-o',str(exe)]
  for k,v in dict(RX_BOUNDARY=rx,CLK_HALF_NS=half,TCO_NS=tco,IDLE_CYCLES=idle).items():cmd+=['-P',f'{top}.{k}={v}']
  cmd+=['fpga/rtl/swd_core.v','fpga/rtl/dap_transfer_block_engine.v','fpga/sim/'+top+'.sv']
  subprocess.run(cmd,check=True,capture_output=True,cwd=root)
  p=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=60,cwd=root);log=p.stdout+p.stderr;(out/(name+'.log')).write_text(log)
  passed=p.returncode==0 and 'PASS' in log
  rows.append(dict(name=name,passed=passed,budget=re.findall(r'BUDGET.*',log)))
  print(('PASS' if passed else 'FAIL')+' '+name,flush=True)
  if not passed:print(log[-1200:],flush=True)
(out/'summary.json').write_text(json.dumps(rows,indent=2))
for rx,half,tco in [(0,5,16),(1,10,1),(1,25,16)]:
 top='tb_swd_stream';name=f'stream_rx{rx}_half{half}_ret{tco}';exe=out/(name+'.vvp')
 cmd=['iverilog','-g2012','-s',top,'-o',str(exe)]
 for k,v in dict(RX_BOUNDARY=rx,CLK_HALF_NS=half,TCO_NS=tco,SAMPLE_RISE=0).items():cmd+=['-P',f'{top}.{k}={v}']
 cmd+=['fpga/rtl/swd_core.v','fpga/rtl/swd_batch_engine.v','fpga/sim/xpm_memory_tdpram.sv','fpga/sim/'+top+'.sv']
 subprocess.run(cmd,check=True,capture_output=True,cwd=root)
 p=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=60,cwd=root);log=p.stdout+p.stderr;(out/(name+'.log')).write_text(log)
 passed=p.returncode==0 and 'ALL SWD WIRE STREAM TESTS PASSED' in log;rows.append(dict(name=name,passed=passed))
 print(('PASS' if passed else 'FAIL')+' '+name,flush=True)
 if not passed:print(log[-1200:],flush=True)
(out/'summary.json').write_text(json.dumps(rows,indent=2))

if any(not r["passed"] for r in rows): raise SystemExit(1)

# Compare FCLK cycles at equal idle settings, independent of clock frequency.
reference={}
for row in rows:
 if row['name'].startswith('rx0_'):
  for b in row.get('budget',[]):
   n,rd,idle,half,cycles,rises,launches=map(int,re.findall(r'=(\d+)',b))
   reference[(n,rd,idle)]=cycles
for row in rows:
 if row['name'].startswith('rx1_'):
  for b in row.get('budget',[]):
   n,rd,idle,half,cycles,rises,launches=map(int,re.findall(r'=(\d+)',b))
   assert cycles<=reference[(n,rd,idle)],(row['name'],b)
print('PASS no packet exceeds main FCLK cycle budget',flush=True)
