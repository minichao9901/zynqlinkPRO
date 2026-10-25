"""OpenOCD 20 KiB SRAM load/dump throughput with full byte verification.

F103 is reset/halted, temporarily clocked at HSI/2 x16 = 64 MHz. No flash is
written. SRAM is backed up after reset/halt and restored before disconnect.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--tag',required=True)
ap.add_argument('--sessions',type=int,default=3)
ap.add_argument('--loops',type=int,default=50)
ap.add_argument('--speed',type=int,default=50000,help='SWCLK in kHz')
ap.add_argument('--bootstrap-speed',type=int,default=50000,
                help='connect and restore at this rate, then switch after HCLK setup')
ap.add_argument('--target-clock',choices=['64','72','96'],default='64')
args=ap.parse_args()
root=Path(__file__).resolve().parents[1]
out=root/'results/optimization'/args.tag
out.mkdir(parents=True,exist_ok=True)
pat=out/'pattern.bin';pat.write_bytes(random.Random(0x20261025).randbytes(20480))
ocd=Path(r'E:\Share\env-windows\openocd-nightly')
rows=[]
for j in range(args.sessions):
    prefix=out/f'session{j}'
    backup=prefix.with_suffix('.backup.bin')
    read=prefix.with_suffix('.read.bin')
    written=prefix.with_suffix('.written.bin')
    restored=prefix.with_suffix('.restored.bin')
    script=prefix.with_suffix('.tcl')
    script.write_text(f'''
init
reset halt
source tools/f103_clock{args.target_clock}.tcl
dump_image {backup.as_posix()} 0x20000000 0x5000
adapter speed {args.speed}
set bench_error [catch {{
load_image {pat.as_posix()} 0x20000000
set t0 [clock milliseconds]
for {{set i 0}} {{$i < {args.loops}}} {{incr i}} {{dump_image {read.as_posix()} 0x20000000 0x5000}}
set t1 [clock milliseconds]
for {{set i 0}} {{$i < {args.loops}}} {{incr i}} {{load_image {pat.as_posix()} 0x20000000}}
set t2 [clock milliseconds]
dump_image {written.as_posix()} 0x20000000 0x5000
echo "MEASURE read_ms=[expr {{$t1-$t0}}] write_ms=[expr {{$t2-$t1}}]"
}} bench_message]
adapter speed {min(args.speed,args.bootstrap_speed)}
load_image {backup.as_posix()} 0x20000000
dump_image {restored.as_posix()} 0x20000000 0x5000
if {{$bench_error}} {{error $bench_message}}
echo "BENCH_COMPLETE"
shutdown
''')
    p=subprocess.run([str(ocd/'bin/openocd.exe'),'-s',str(ocd/'share/openocd/scripts'),
        '-f','tools/openocd_dap.cfg','-c',f'adapter speed {min(args.speed,args.bootstrap_speed)}', '-f',str(script)],
        cwd=root,capture_output=True,text=True,errors='replace',timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW)
    text=p.stdout+p.stderr
    prefix.with_suffix('.log').write_text(text,encoding='utf-8')
    m=re.search(r'MEASURE read_ms=(\d+) write_ms=(\d+)',text)
    if p.returncode or not m or 'BENCH_COMPLETE' not in text:raise RuntimeError(text)
    if read.read_bytes()!=pat.read_bytes() or written.read_bytes()!=pat.read_bytes():
        raise RuntimeError('SRAM data mismatch')
    if restored.read_bytes()!=backup.read_bytes():raise RuntimeError('SRAM restore mismatch')
    r,w=map(int,m.groups())
    row={'session':j,'bytes_per_direction':20480*args.loops,'read_ms':r,'write_ms':w,
        'read_MB_s':20480*args.loops/r/1000,'write_MB_s':20480*args.loops/w/1000,
        'data_match':True,'restore_match':True}
    rows.append(row);print(json.dumps(row),flush=True)
result={'requested_SWCLK_kHz':args.speed,'target_HCLK_MHz':int(args.target_clock),'size_bytes':20480,
        'loops':args.loops,'pattern_sha256':hashlib.sha256(pat.read_bytes()).hexdigest(),
        'sessions':rows,'read_MB_s':sum(x['bytes_per_direction'] for x in rows)/sum(x['read_ms'] for x in rows)/1000,
        'write_MB_s':sum(x['bytes_per_direction'] for x in rows)/sum(x['write_ms'] for x in rows)/1000}
(out/'results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
