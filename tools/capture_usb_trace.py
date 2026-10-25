"""Read/clear the noncached USB trace using addresses from the current ELF."""
import argparse
from pathlib import Path
import subprocess
import sys

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--elf', type=Path, default=Path('build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf'))
ap.add_argument('--output', type=Path, default=Path('results/optimization/usb_trace.bin'))
ap.add_argument('--clear', action='store_true')
a = ap.parse_args()
nm = Path(r'E:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-nm.exe')
symbols = {}
for line in subprocess.check_output([str(nm), str(a.elf)], text=True).splitlines():
    fields = line.split()
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)
if a.clear:
    action = f"mwr 0x{symbols['dap_trace_count']:08x} 0"
else:
    a.output.parent.mkdir(parents=True, exist_ok=True)
    base, end = symbols['__dap_trace_start'], symbols['__dap_trace_end']
    action = f'mrd -bin -file {{{a.output.resolve().as_posix()}}} 0x{base:08x} {(end-base+3)//4}'
script = Path('build/capture_usb_trace.tcl')
script.write_text('connect\ntargets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}\n' + action + '\ndisconnect\nexit\n')
subprocess.run([sys.executable, 'tools/run_xsct.py', str(script)], check=True)
