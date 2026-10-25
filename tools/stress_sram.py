"""Randomize, write and fully compare every 20 KiB SRAM iteration."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--tag',required=True)
ap.add_argument('--speed',type=int,default=60000)
ap.add_argument('--iterations',type=int,default=100)
ap.add_argument('--target-clock',choices=['64','72','96'],default='64')
args=ap.parse_args()
root=Path(__file__).resolve().parents[1]
out=root/'results/optimization'/args.tag
out.mkdir(parents=True,exist_ok=True)
rng=random.Random(0x20261026)
for i in range(args.iterations):
    (out/f'pattern{i}.bin').write_bytes(rng.randbytes(20480))
backup=out/'backup.bin';restored=out/'restored.bin'
script=out/'stress.tcl'
script.write_text(f'''
init
reset halt
source tools/f103_clock{args.target_clock}.tcl
dump_image {backup.as_posix()} 0x20000000 0x5000
adapter speed {args.speed}
set test_error [catch {{
for {{set i 0}} {{$i < {args.iterations}}} {{incr i}} {{
 load_image {out.as_posix()}/pattern$i.bin 0x20000000
 dump_image {out.as_posix()}/read$i.bin 0x20000000 0x5000
}}
}} test_message]
adapter speed 50000
load_image {backup.as_posix()} 0x20000000
dump_image {restored.as_posix()} 0x20000000 0x5000
if {{$test_error}} {{error $test_message}}
echo STRESS_COMPLETE
shutdown
''')
ocd=Path(r'E:/Share/env-windows/openocd-nightly')
p=subprocess.run([str(ocd/'bin/openocd.exe'),'-s',str(ocd/'share/openocd/scripts'),
                  '-f','tools/openocd_dap.cfg','-f',str(script)],cwd=root,
                 capture_output=True,text=True,errors='replace',timeout=90,
                 creationflags=subprocess.CREATE_NO_WINDOW)
log=p.stdout+p.stderr
(out/'openocd.log').write_text(log,encoding='utf-8')
rows=[]
for i in range(args.iterations):
    pattern=(out/f'pattern{i}.bin').read_bytes()
    read=out/f'read{i}.bin'
    rows.append({'iteration':i,'match':read.exists() and read.read_bytes()==pattern,
                 'sha256':hashlib.sha256(pattern).hexdigest()})
restore_match=backup.exists() and restored.exists() and backup.read_bytes()==restored.read_bytes()
result={'requested_SWCLK_kHz':args.speed,'target_HCLK_MHz':int(args.target_clock),'iterations':args.iterations,
        'bytes_per_iteration':20480,'every_iteration_matches':all(r['match'] for r in rows),
        'restore_match':restore_match,'openocd_returncode':p.returncode,'rows':rows}
(out/'results.json').write_text(json.dumps(result,indent=2))
if p.returncode or 'STRESS_COMPLETE' not in log or not result['every_iteration_matches'] or not restore_match:
    raise RuntimeError(f'SRAM stress failed; see {out}/openocd.log and results.json')
print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
