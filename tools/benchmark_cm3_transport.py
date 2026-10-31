"""Real-CM3 SRAM/RTT/HSS RTL throughput at the board's realized link settings."""
import argparse,hashlib,json,os,re,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]


def decode(log):
    result={'passed':'PASS SIM_TRANSPORT_BENCH' in log and not re.search(r'\b(?:Fatal|Error|FAIL)\b',log,re.I)}
    result['SRAM']=[dict(read=int(rd),bytes=int(n),elapsed_ns=float(ns),MB_s=float(rate),WAITs=int(wait)) for rd,n,ns,rate,wait in
                    re.findall(r'SIM_SRAM read=(\d+) bytes=(\d+) elapsed_ns=([\d.]+) MBps=([\d.]+) waits=(\d+)',log)]
    result['RTT']=[dict(bytes=int(n),elapsed_ns=float(ns),MB_s=float(rate),WAITs=int(wait)) for n,ns,rate,wait in
                   re.findall(r'SIM_RTT bytes=(\d+) elapsed_ns=([\d.]+) MBps=([\d.]+) waits=(\d+)',log)]
    result['HSS']=[dict(period_ticks=int(p),produced=int(n),skipped=int(k),elapsed_ns=float(ns),effective_Hz=float(hz),skip_percent=float(loss)) for p,n,k,ns,hz,loss in
                   re.findall(r'SIM_HSS period=(\d+) produced=(\d+) skipped=(\d+) elapsed_ns=([\d.]+) Hz=([\d.]+) skip_percent=([\d.]+)',log)]
    if not result['passed']:result['failure']=next((v for v in log.splitlines() if re.search(r'\b(?:Fatal|Error|FAIL)\b',v,re.I)),'Missing final benchmark PASS')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport',choices=['swd','jtag'],required=True)
    p.add_argument('--board-settings',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--use-current-first-log',action='store_true',help='Import the already completed first-rate benchmark from this top')
    p.add_argument('--rebuild',action='store_true')
    p.add_argument('--return-delay-ns',type=float,default=16.0,help='Explicit model-only pad/return latency; does not change recorded board settings')
    p.add_argument('--first-sram-log',type=Path,help='Import separately validated first-rate SRAM stages; subsequent RTT/HSS rerun must complete')
    a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    top='tb_cm3_'+a.transport;work=Path(os.environ.get('ZYNQLINK_WORK_DIR',str(r.parent/'zynqlinkPRO-work')))/'cm3_sim'/top
    source_files=list((r/'fpga/rtl').glob('*.v'))+[r/'fpga/sim'/f'{top}.sv',r/'fpga/sim/cm3_perf_tasks.svh',r/'fpga/sim/cm3_target.sv']
    sources={str(v.relative_to(r)):hashlib.sha256(v.read_bytes()).hexdigest() for v in source_files}
    settings=[v for v in json.loads(a.board_settings.read_text())['rows'] if v['transport']==a.transport]
    rows=[]
    for idx,row in enumerate(settings):
        fclk=row['FCLK_Hz'];cfg=int(row['cfg'],16);mhz=row['requested_Hz']//1000000
        args=['benchmark','target_clk_ns=10.416667']
        if a.transport=='swd':
            args += [f'half_ns={5e8/fclk:.9f}',f'transfer_delay={((cfg>>13)&15)+(((cfg>>28)&15)<<4)}',f'narrow_clock={(cfg>>19)&1}',f'rx_boundary={(cfg>>18)&1}',f'phase={(cfg>>17)&1}',f'return_ns={a.return_delay_ns:g}']
        else:
            mode=row['JTAG_sampling_mode']
            args += [f'clk_ns={1e9/fclk:.9f}','delay_tdo',f'tdo_ns={a.return_delay_ns:g}','bypass']
            if mode&16:args+=['late']
            if mode&1:args+=['q1']
        if idx==0 and a.use_current_first_log:
            log=(work/'xsim.log').read_text(errors='replace')
            assert 'testplusarg benchmark' in log and decode(log)['passed'],'Current first benchmark is not complete'
            rc=0
            if 'testplusarg skip_sram' in log:args+=['skip_sram']
        else:
            cmd=[sys.executable,'tools/run_cm3_sim.py','--top',top]+(['--rebuild'] if idx==0 and a.rebuild else [])+args
            log_path=work/'xsim.log'
            previous_log_stamp=log_path.stat().st_mtime_ns if log_path.exists() else None
            done=subprocess.run(cmd,cwd=r,capture_output=True,text=True,errors='replace',timeout=3600)
            fresh_log=log_path.exists() and log_path.stat().st_mtime_ns!=previous_log_stamp
            log=log_path.read_text(errors='replace') if fresh_log else done.stdout+done.stderr
            rc=done.returncode
        dest=out/f'{a.transport}_{mhz}.log';dest.write_text(log)
        item=dict(transport=a.transport,requested_Hz=row['requested_Hz'],FCLK_Hz=fclk,actual_link_Hz=row['actual_link_Hz'],
                  target_HCLK_Hz=96000000,return_delay_ns=a.return_delay_ns,USB_modeled=False,args=args,returncode=rc,**decode(log))
        if idx==0 and a.first_sram_log:
            earlier=a.first_sram_log.read_text(errors='replace');sram=decode(earlier)['SRAM']
            assert len(sram)==2 and {v['read'] for v in sram}=={0,1} and all(v['bytes']==1024 for v in sram)
            item['SRAM']=sram
            item['SRAM_stage_note']='Both SRAM payloads verified before an unrelated premature RTT RdOff assertion. RTT/HSS are from the completed rerun.'
            (out/f'{a.transport}_{mhz}_sram_stage.log').write_text(earlier)
        item['passed']=item['passed'] and len(item['SRAM'])==2 and len(item['RTT'])==1 and len(item['HSS'])>=2
        rows.append(item)
        (out/f'{a.transport}.json').write_text(json.dumps(dict(source_sha256=sources,rows=rows),indent=2)+'\n')
        print(a.transport,mhz,'PASS' if item['passed'] else 'FAIL',flush=True)
    return int(any(not v['passed'] for v in rows))


if __name__=='__main__':raise SystemExit(main())
