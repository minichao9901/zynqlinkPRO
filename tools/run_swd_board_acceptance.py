"""Run the same preserved-RAM SRAM/HSS/RTT acceptance for an explicit bit/ELF pair."""
import argparse,json,subprocess,sys,time
from pathlib import Path
from probe_build_info import provenance
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--label',required=True);p.add_argument('--bit',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--stage',choices=['high','low','all','api2'],default='all');p.add_argument('--loops',type=int,default=100)
    p.add_argument('--output-root',type=Path,default=ROOT/'build/board_comparison_20261028')
    a=p.parse_args();out=(a.output_root/a.label).resolve();out.mkdir(parents=True,exist_ok=True)
    report=dict(label=a.label,artifacts=provenance(a.bit,a.elf),runs=[])
    dest=out/('acceptance_'+a.stage+'.json')
    def run(name,tool,args,required=True,timeout=300):
        cmd=[sys.executable,str(ROOT/'tools'/tool),*map(str,args)]
        t=time.monotonic();r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,errors='replace',timeout=timeout)
        (out/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        row=dict(name=name,command=cmd,returncode=r.returncode,seconds=round(time.monotonic()-t,2),required=required)
        report['runs'].append(row);dest.write_text(json.dumps(report,indent=2))
        print(('PASS' if r.returncode==0 else 'FAIL')+' '+name+' '+str(row['seconds'])+'s',flush=True)
        if r.returncode:print((r.stdout+r.stderr)[-1400:],flush=True)
        if required and r.returncode:raise SystemExit(1)
    art=['--bit',a.bit.resolve(),'--elf',a.elf.resolve()]
    if a.stage=='api2':
        for speed in [50000,60000]:
            run(f'sram_api_p2_{speed}','benchmark_cmsis_sram.py',['--speed',speed,'--sessions',3,'--loops',a.loops,'--prefix-words',2,'--output',out/f'sram_api_p2_{speed}.json'])
    if a.stage in ['high','all']:
        run('functional','test_probe_board.py',['--services','both','--seconds',.5,'--output',out/'functional.json'])
        for speed in [50000,60000]:
            run(f'sram_api_{speed}','benchmark_cmsis_sram.py',['--speed',speed,'--sessions',3,'--loops',a.loops,'--output',out/f'sram_api_{speed}.json'])
            run(f'sram_openocd_{speed}','benchmark_sram_optimized.py',['--tag',a.label+'_'+str(speed),'--output-dir',out/f'openocd_{speed}','--sessions',3,'--loops',a.loops,'--speed',speed,'--no-reset','--clock-script','none','--openocd-exe',r'E:/zynqlinkPRO_batch/build/openocd_runtime/openocd.exe','--scripts',r'E:/zynqlinkPRO/build/openocd-src/tcl'])
        run('hss_static1','benchmark_probe_stream.py',['--speeds','50000000,60000000','--variables','1','--periods','48,40,32,24','--seconds',3,'--repeats',2,'--output',out/'hss_static1.json',*art],timeout=180)
        run('hss_static8','benchmark_probe_stream.py',['--speeds','50000000,60000000','--variables','8','--periods','240,200,192','--seconds',3,'--repeats',2,'--output',out/'hss_static8.json',*art],timeout=160)
        run('hss_dynamic','benchmark_hss_dynamic.py',['--speed',60000000,'--periods','48,40,32,24','--seconds',3,'--output',out/'hss_dynamic.json',*art],timeout=90)
        run('rtt_high','benchmark_rtt_forward.py',['--speeds','50000000,60000000','--chunks','2048','--seconds',5,'--repeats',2,'--output',out/'rtt_high.json',*art],timeout=100)
    if a.stage in ['low','all']:
        run('sram_low','test_swd_lowfreq_board.py',['--output',out/'sram_low.json',*art],required=False,timeout=180)
        for speed in [1000000,10000000,25000000,35000000]:
            run(f'rtt_low_{speed}','benchmark_rtt_forward.py',['--speeds',speed,'--chunks','1024','--seconds',2,'--repeats',1,'--output',out/f'rtt_low_{speed}.json',*art],required=False,timeout=60)
        for speed in [10000000,15000000,25000000,35000000]:
            run(f'hss_low_{speed}','benchmark_probe_stream.py',['--speeds',speed,'--variables','1','--periods','2400','--seconds',1,'--repeats',1,'--output',out/f'hss_low_{speed}.json',*art],required=False,timeout=40)
    print(dest,flush=True)
if __name__=='__main__':main()
