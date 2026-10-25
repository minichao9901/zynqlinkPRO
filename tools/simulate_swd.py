"""Run wire-level SWD regressions, including expected bad sampling windows."""
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
out=root/'results/optimization/simulation'
out.mkdir(parents=True,exist_ok=True)
sources=['fpga/sim/xpm_memory_tdpram.sv','fpga/rtl/swd_core.v',
         'fpga/rtl/swd_batch_engine.v','fpga/sim/tb_swd_stream.sv']
cases=[(1,1,5,0,True),(1,16,5,0,True),(0,16,5,0,True),
       (0,16,4.166667,0,True),(0,20,3.055556,0,True),
       (0,20,3.055556,1,True),(1,16,3.055556,0,False),
       (0,1,5,0,False)]
rows=[]
for phase,tco,half,idle,expected in cases:
    name=f'phase{phase}_tco{tco}_half{half}_idle{idle}'
    executable=root/'build'/f'{name}.vvp'
    params={'SAMPLE_RISE':phase,'TCO_NS':tco,'CLK_HALF_NS':half,'IDLE_CYCLES':idle}
    subprocess.run(['iverilog','-g2012','-s','tb_swd_stream',
                    *[f'-Ptb_swd_stream.{k}={v}' for k,v in params.items()],
                    '-o',str(executable),*sources],cwd=root,check=True,capture_output=True)
    p=subprocess.run(['vvp',str(executable)],cwd=root,capture_output=True,text=True,timeout=60)
    (out/f'{name}.log').write_text(p.stdout+p.stderr)
    row={**params,'passed':p.returncode==0,'expected_pass':expected,
         'matches_expectation':(p.returncode==0)==expected}
    rows.append(row)
    print(json.dumps(row),flush=True)
(out/'results.json').write_text(json.dumps(rows,indent=2))
if not all(r['matches_expectation'] for r in rows):raise RuntimeError('Unexpected SWD regression')
