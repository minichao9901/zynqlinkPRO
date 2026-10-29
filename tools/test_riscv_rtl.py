"""Run RISC-V IDCODE and full PL SBA/RTT/HSS regressions."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
out = root / 'build/riscv_sim'
out.mkdir(parents=True, exist_ok=True)
for top in ('tb_jtag_riscv', 'tb_riscv_pipeline'):
    sources = [root / 'fpga/rtl' / name for name in ('jtag_core.v', 'jtag_shift.v')]
    if top == 'tb_jtag_riscv':
        sources += [root / 'fpga/sim/jtag_dtm_model.sv']
    else:
        sources += [root / 'fpga/rtl' / name for name in (
            'swd_core.v', 'swd_controller.v', 'swd_batch_engine.v',
            'dap_transfer_block_engine.v', 'probe_sample_engine.v',
            'probe_rtt_engine.v', 'probe_stream_engine.v')]
        sources += [root / 'fpga/sim' / name for name in (
            'riscv_sba_model.sv', 'xpm_memory_tdpram.sv', 'tb_packet_axi.sv')]
    sources.append(root / 'fpga/sim' / (top + '.sv'))
    exe = out / (top + '.vvp')
    subprocess.run(['iverilog', '-g2012', '-s', top, '-o', str(exe), *map(str, sources)], check=True)
    result = subprocess.run(['vvp', str(exe)], capture_output=True, text=True, timeout=180)
    (out / (top + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    print(result.stdout + result.stderr, end='', flush=True)
    assert result.returncode == 0, top
