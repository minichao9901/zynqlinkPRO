"""Exercise autonomous sample RTL with a posted-read AHB-AP model."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
out = root / 'build/probe_sim'
out.mkdir(parents=True, exist_ok=True)
exe = out / 'sample.vvp'
subprocess.run(['iverilog', '-g2012', '-s', 'tb_probe_sample', '-o', str(exe),
                str(root/'fpga/rtl/probe_sample_engine.v'),
                str(root/'fpga/sim/tb_probe_sample.sv')], check=True)
r = subprocess.run(['vvp', str(exe)], capture_output=True, text=True, timeout=30)
(out/'sample.log').write_text(r.stdout+r.stderr)
print(r.stdout+r.stderr, end='')
assert r.returncode == 0
