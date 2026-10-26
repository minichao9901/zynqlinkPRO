"""Run synchronous-BRAM, retry/error, and AXI packet-engine regressions."""
import argparse
import json
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--compare-ref', help='Also compile packet RTL from this Git ref')
a = ap.parse_args()
out = root/'build/packet_pipeline_sim'
out.mkdir(parents=True, exist_ok=True)
results = []

def run(name, rtl, label, integration=False):
    src = root/'fpga/sim'/f'{name}.sv'
    top = re.search(r'module\s+(\w+)', src.read_text())[1]
    exe = out/f'{label}_{name}.vvp'
    files = [rtl, src]
    if integration:
        files += [root/'fpga/rtl'/f for f in ['swd_core.v', 'swd_controller.v', 'swd_batch_engine.v']]
        files += [root/'fpga/sim/xpm_memory_tdpram.sv']
    subprocess.run(['iverilog', '-g2012', '-s', top, '-o', str(exe), *map(str, files)], check=True)
    r = subprocess.run(['vvp', str(exe)], capture_output=True, text=True, timeout=60)
    (out/f'{label}_{name}.log').write_text(r.stdout+r.stderr)
    assert r.returncode == 0, r.stdout+r.stderr
    cycles = [dict(zip(['count', 'read', 'cycles'], map(int, m))) for m in re.findall(
        r'CYCLES count=(\d+) read=(\d+) cycles=(\d+)', r.stdout)]
    results.append({'label': label, 'test': name, 'passed': True, 'cycles': cycles})
    print(f'PASS {label} {name}', cycles if cycles else '', flush=True)

rtl = root/'fpga/rtl/dap_transfer_block_engine.v'
for name in ['tb_dap_transfer_block_engine', 'tb_engine_cases', 'tb_engine_retry', 'tb_engine_lat1', 'tb_packet_contract']:
    run(name, rtl, 'current')
run('tb_packet_axi', rtl, 'current', integration=True)
if a.compare_ref:
    baseline = subprocess.check_output(['git', 'show', f'{a.compare_ref}:fpga/rtl/dap_transfer_block_engine.v'], cwd=root)
    ref = out/'baseline_packet.v'
    ref.write_bytes(baseline)
    run('tb_packet_contract', ref, 'baseline')
dest = root/'results/optimization/packet_pipeline_sim.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(results, indent=2))
