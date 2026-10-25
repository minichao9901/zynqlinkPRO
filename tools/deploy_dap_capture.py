"""Program a RAM bitstream/ELF and record COM5 startup diagnostics."""
import argparse
from pathlib import Path
import subprocess
import sys
import time
import serial

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('elf');ap.add_argument('bit');ap.add_argument('--tag',default='dma_boot')
args=ap.parse_args()
out=Path('results/optimization');out.mkdir(exist_ok=True)
with serial.Serial('COM5',115200,timeout=.2) as uart:
    uart.reset_input_buffer()
    p=subprocess.run([sys.executable,'tools/run_xsct.py','tools/download_dap_fpga.tcl',args.elf,args.bit],
        capture_output=True,text=True,errors='replace',timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW)
    (out/(args.tag+'_jtag.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
    deadline=time.monotonic()+2
    data=bytearray()
    while time.monotonic()<deadline:data.extend(uart.read(4096))
    (out/(args.tag+'_uart.log')).write_bytes(data)
    print(p.stdout[-600:]);print(data.decode(errors='replace'))
    if p.returncode:raise SystemExit(p.returncode)
