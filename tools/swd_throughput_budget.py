"""Compare SWD framing limits with the real core/packet FSM cycle budget.

Simulation excludes USB, DMA, PS and target WAIT responses. Zero idle remains
experimental pending board verification; pyOCD 0.46 defaults to two.
"""
import json
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
out=root/'build/wire_budget'
out.mkdir(parents=True,exist_ok=True)
rows=[]
for idle in [0,1,2]:
    exe=out/f'idle{idle}.vvp'
    subprocess.run(['iverilog','-g2012','-s','tb_packet_wire_budget',
                    '-P',f'tb_packet_wire_budget.IDLE_CYCLES={idle}',
                    '-o',str(exe),'fpga/rtl/dap_transfer_block_engine.v',
                    'fpga/rtl/swd_core.v','fpga/sim/tb_packet_wire_budget.sv'],cwd=root,check=True)
    r=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30)
    (out/f'idle{idle}.log').write_text(r.stdout+r.stderr)
    assert r.returncode==0 and 'PASS' in r.stdout,r.stdout+r.stderr
    for m in re.findall(r'BUDGET words=(\d+) read=(\d+) idle=(\d+) half_ns=(\d+) cycles=(\d+) rises=(\d+) launches=(\d+)',r.stdout):
        row=dict(zip(['words','read','idle','simulation_half_ns','FCLK_cycles','SWCLK_rises','SWD_transfers'],map(int,m)))
        row['rtl_MB_s_at_SWCLK_50MHz']=row['words']*4*100/row['FCLK_cycles']
        row['rtl_MB_s_at_SWCLK_60MHz']=row['words']*4*120/row['FCLK_cycles']
        rows.append(row)
        if row['words']==1022:print(row)
result={'frame':{'request':8,'request_turnaround':1,'ACK':3,'data':32,'parity':1,'direction_turnaround':1,'total_SWCLK':46},
        'ideal_MB_s':{str(mhz):{'idle0':4*mhz/46,'idle1':4*mhz/47,'idle2':4*mhz/48} for mhz in [50,60]},
        'simulated_real_RTL':rows,
        'limits':'No USB/PS/DMA, no target WAIT. FCLK=2*SWCLK; 1022 data words plus final AP drain. Uses current working-tree RTL.'}
dest=root/'results/optimization/swd_throughput_budget.json'
dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps(result,indent=2))
