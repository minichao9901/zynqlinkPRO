"""Plan/run the F103ZE RAM-only probe regression with an explicit bit/ELF/init tuple.

Default is plan-only. --execute loads the tuple once, then runs sequential cases
with target SRAM/pin/run-state restoration. The caller must hold the single-board
reservation; this runner is not an inter-process hardware lock.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bit',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--ps-init',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True,help='new evidence directory')
    p.add_argument('--profile',type=int,choices=[50,60],default=60)
    p.add_argument('--restore-swj',choices=['0','1','2','4'],default='2')
    p.add_argument('--execute',action='store_true',help='explicitly authorize loading and board operations')
    p.add_argument('--openocd-exe',default='E:/Share/env-windows/openocd-nightly/bin/openocd.exe')
    p.add_argument('--openocd-scripts',default='E:/Share/env-windows/openocd-nightly/share/openocd/scripts')
    a=p.parse_args();dest=a.out.resolve()
    bit,elf,init=[x.resolve() for x in [a.bit,a.elf,a.ps_init]]
    for path in [bit,elf,init]:
        if not path.is_file():p.error('Missing input: '+str(path))
    art=['--bit',str(bit),'--elf',str(elf)]
    speed=a.profile*1000000;khz=str(a.profile*1000)
    speeds='1000000,10000000,25000000,30000000,35000000,50000000'+(',60000000' if a.profile==60 else '')
    jobs=[('sram',['benchmark_sram_matrix.py','--transport','both','--speeds',speeds,'--seconds','0.6','--repeats','5',*art])]
    for tr in ['swd','jtag']:
        for hz in speeds.split(','):
            jobs.append((f'rtt_{tr}_{hz}',['benchmark_rtt_forward.py','--transport',tr,'--speeds',hz,'--chunks','1024','--seconds','3','--repeats','3',*art]))
        jobs.extend([
            ('hss_'+tr,['benchmark_hss_matrix.py','--transports',tr,'--speeds',str(speed),'--seconds','0.5',*art]),
            ('hss_dynamic_'+tr,['benchmark_hss_dynamic.py','--transport',tr,'--speed',str(speed),'--periods','120,48,40,32,24','--seconds','2',*art]),
            ('hss_8vars_'+tr,['benchmark_probe_stream.py','--transport',tr,'--speeds',str(speed),'--variables','8','--periods','1200,480,240,200,192','--seconds','1','--repeats','3',*art])])
    jobs.extend([
        ('functional',['test_probe_board.py','--services','both','--seconds','0.5','--speed-hz',str(speed),*art]),
        ('jtag_unaligned',['test_jtag_board.py','--speeds',str(speed)]),
        ('cmsis_depth16',['benchmark_cmsis_sram.py','--speed',khz,'--sessions','3','--loops','100','--depth','16']),
        ('openocd',['benchmark_sram_optimized.py','--tag','combined_'+str(a.profile),'--output-dir',str(dest/'openocd'),'--sessions','3','--loops','30','--speed',khz,'--no-reset','--clock-script','none','--openocd-exe',a.openocd_exe,'--scripts',a.openocd_scripts])])
    plan=[]
    for name,options in jobs:
        child=[sys.executable,'-X','utf8',str(ROOT/'tools'/options[0]),*options[1:]]
        output=dest/(name+'.json');fixture=dest/(name+'_fixture.json')
        if name!='openocd':child+=['--output',str(output)]
        command=[sys.executable,'-X','utf8',str(ROOT/'tools/run_f103_jtag_fixture.py'),'--restore-swj',a.restore_swj,'--output',str(fixture),'--',*child]
        plan.append(dict(name=name,output=str(output),fixture=str(fixture),command=command))
    identity={k:dict(path=str(v),sha256=hashlib.sha256(v.read_bytes()).hexdigest()) for k,v in [('bit',bit),('elf',elf),('ps_init',init)]}
    if not a.execute:
        print(json.dumps(dict(execute=False,identity=identity,jobs=plan),indent=2));return
    if not Path(a.openocd_exe).is_file() or not Path(a.openocd_scripts).is_dir():p.error('OpenOCD executable/scripts missing')
    dest.mkdir(parents=True,exist_ok=False)
    (dest/'plan.json').write_text(json.dumps(dict(identity=identity,jobs=plan),indent=2)+'\n')
    temp=dest/'tmp';temp.mkdir();env=os.environ.copy();env['TEMP']=env['TMP']=str(temp)
    with (dest/'load.log').open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,str(ROOT/'tools/run_xsct.py'),str(ROOT/'tools/download_dap_fpga.tcl'),str(elf),str(bit),str(init)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    rows=[]
    for job in plan:
        start=time.monotonic();output=Path(job['output'])
        with output.with_suffix('.log').open('w',encoding='utf-8') as log:
            result=subprocess.run(job['command'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        value=json.loads(output.read_text()) if output.exists() else {}
        fixture=json.loads(Path(job['fixture']).read_text())
        passed=result.returncode==0 and value.get('passed',True) and not any(value.get(k) for k in ['recover_error','failure','error'])
        passed=passed and fixture.get('run_halt_restore_match') and fixture.get('APB2ENR_restore_match') and fixture.get('MAPR_readable_restore_match')
        if value.get('backup_sha256'):passed=passed and value.get('restore_match')
        if value.get('sessions'):passed=passed and all(x.get('restore_match') for x in value['sessions'])
        if job['name']=='openocd':
            check=json.loads((dest/'openocd/results.json').read_text());passed=passed and all(x.get('restore_match') for x in check['sessions'])
        rows.append(dict(**job,returncode=result.returncode,passed=bool(passed),seconds=time.monotonic()-start,restore_match=value.get('restore_match'),fixture_restore=fixture.get('run_halt_restore_match')))
        (dest/'runs.json').write_text(json.dumps(rows,indent=2)+'\n');print(job['name'],'PASS' if passed else 'FAIL',flush=True)
        if not passed:raise RuntimeError('Case failed; stop and inspect saved backup/restore evidence: '+job['name'])


if __name__=='__main__':main()
