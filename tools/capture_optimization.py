"""Run finite SWD traffic and capture a 1 ms LA window concurrently."""
from pathlib import Path
import argparse
import subprocess
import sys
import time

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('name')
ap.add_argument('--dpid', action='store_true')
ap.add_argument('--speed', type=int, default=50000, help='requested SWCLK in kHz')
ap.add_argument('--allow-errors', action='store_true')
args=ap.parse_args()
name = args.name
out = Path('results/optimization')
out.mkdir(exist_ok=True)
with (out/(name+'_traffic.log')).open('w') as log:
    cmd = [r'E:\Share\env-windows\openocd-nightly\bin\openocd.exe',
        '-s', r'E:\Share\env-windows\openocd-nightly\share\openocd\scripts',
        '-f','tools/openocd_dap.cfg','-c',f'adapter speed {args.speed}',
        '-f','tools/ocd_optimization_traffic.tcl']
    if args.dpid:
        cmd=[sys.executable,'tools/la/dpid_traffic.py','--speed',str(args.speed)]
        if args.allow_errors: cmd.append('--allow-errors')
    p = subprocess.Popen(cmd,
        stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        time.sleep(1)
        subprocess.run([sys.executable,'tools/la/la_capture_export.py','--rate','500000000',
            '--time','0.001','--threshold','1.65','--out',str((out/(name+'.csv')).resolve())],
            timeout=45, check=True)
        if p.wait(timeout=20) != 0:
            raise RuntimeError('SWD traffic failed; inspect '+str(out/(name+'_traffic.log')))
    finally:
        if p.poll() is None: p.terminate(); p.wait(timeout=5)
print(out/(name+'.csv'))
