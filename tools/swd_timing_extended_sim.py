"""Verify exposed timing registers, serial windows, production C and services.

No USB/XSCT/board operations. --scan records both working and failing physical
return windows; those discovery outcomes are not reported as functional passes.
"""
from pathlib import Path
import argparse
import itertools
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import swd_timing_sim as sim

ROOT=sim.ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--groups',default='csr,wire,host,m0')
    ap.add_argument('--scan',action='store_true')
    args=ap.parse_args();groups=set(args.groups.split(','))
    if groups-{'csr','wire','host','m0'}:ap.error('Unknown group')
    sim.OUT=ROOT/'build/swd_timing_extended';sim.OUT.mkdir(exist_ok=True)
    rtl=ROOT/'fpga/rtl';tb=ROOT/'fpga/sim';rows=[]
    core=[rtl/'swd_core.v',rtl/'swj_clk_gen.v']
    controller=[rtl/f for f in ['swd_timing_regs.v','swd_controller.v','swd_batch_engine.v',
        'dap_transfer_block_engine.v','probe_sample_engine.v','probe_rtt_engine.v',
        'probe_stream_engine.v']]+[tb/'sim_primitives.v',tb/'xpm_memory_tdpram.sv']
    if 'csr' in groups:
        e=sim.compile_top('tb_swd_timing_config',core+controller+
            [tb/'tb_swd_timing_config.sv'],'registers')
        rows.append(sim.simulate(e,'registers'))
    wire_sources=core+[rtl/'swd_batch_engine.v',tb/'xpm_memory_tdpram.sv',tb/'tb_swd_timing_wire.sv']
    def wire(name,params):
        e=sim.compile_top('tb_swd_timing_wire',wire_sources,name,params)
        return sim.simulate(e,name)
    if 'wire' in groups:
        for name,hq,ack,data,tco in [
            ('compat',65536,65536,65536,16),
            ('coincident',65536,0,0,16),
            ('q1_q2',65536,196608,327680,16),
            ('q2_q1',65536,327680,196608,16),
            ('raw',65536,458752,458752,24),
            ('early',131072,131072,131072,24),
            ('different_offsets',131072,131072,327680,40),
            ('late',131072,196608,196608,40),
            ('q16_1p2',78644,196608,196608,24),
            ('q16_1p5',98304,196608,196608,32),
            ('q16_early',98304,131072,131072,24),
            ('slow_early',196608,131072,131072,40)]:
            rows.append(wire(name,dict(SAMPLE_RISE=0,HALF_Q=hq,
                ACK_SAMPLE=ack,DATA_SAMPLE=data,TCO_NS=tco)))
        rows.append(wire('stage_periods',dict(SAMPLE_RISE=0,HALF_Q=131072,
            ACK_Q=196608,TURN_Q=196608,SWJ_Q=655360,
            ACK_SAMPLE=131072,DATA_SAMPLE=131072,TCO_NS=40)))
    if 'host' in groups:
        for name in ['test_swd_timing_host.py','test_probe_host.py']:
            p=subprocess.run([sys.executable,str(ROOT/'tools'/name)],cwd=ROOT,
                             capture_output=True,text=True,timeout=120)
            log=p.stdout+p.stderr;(sim.OUT/(name+'.log')).write_text(log)
            ok=p.returncode==0 and 'PASS' in log
            rows.append(dict(name=name,passed=ok,matched=ok))
            print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    if 'm0' in groups:
        from run_cortexm0_regress import DEFAULT_MODEL,MODEL
        checked=sim.instrument_core(sim.OUT)
        work,env=sim.compile_xsim(checked+controller+
            [DEFAULT_MODEL/f for f in MODEL]+[tb/'tb_cortexm0_link.sv'])
        profiles=[
            ('compat_packets',['+timing=1','+idle=1','+packets']),
            ('independent_services',['+timing=1','+idle=1','+services','+timing_reject_busy',
                '+ack_sample=196608','+data_sample=327680']),
            ('early_services',['+timing=1','+idle=1','+services','+timing_reject_busy',
                '+halfq=131072','+ack_sample=131072','+data_sample=131072','+return_ns=24.0']),
            ('fraction_services',['+timing=1','+idle=1','+services','+timing_reject_busy',
                '+halfq=78644','+ack_sample=196608','+data_sample=196608','+return_ns=20.0']),
            ('stage_periods_m0',['+timing=1','+words=16','+idle=1','+halfq=131072',
                '+ackq=65536','+turnq=196608','+swjq=655360',
                '+ack_sample=327680','+data_sample=131072','+return_ns=24.0']),
        ]
        for name,params in profiles:rows.append(sim.simulate_xsim(work,env,name,params))
        # Paired boundary test: the exact same half period/return delay passes
        # with offset zero above, and fails at the old end slot. Keep the
        # observed rejection separate from the positive service result.
        rows.append(sim.simulate_xsim(work,env,'late_window_rejection',[
            '+timing=1','+words=2','+idle=1','+halfq=131072',
            '+ack_sample=196608','+data_sample=196608','+return_ns=24.0'],expected_ack='4'))
    if args.scan:
        def point(item):
            hq,source,offset,tco=item;cfg=(source<<17)|(65536 if offset<0 else offset)
            name=f'scan_{hq}_{source}_{offset}_{tco}'
            e=sim.compile_top('tb_swd_timing_wire',wire_sources,name,dict(
                SAMPLE_RISE=0,HALF_Q=hq,ACK_SAMPLE=cfg,DATA_SAMPLE=cfg,TCO_NS=tco))
            p=subprocess.run(['vvp',str(e)],capture_output=True,text=True,timeout=15)
            log=p.stdout+p.stderr;(sim.OUT/(name+'.log')).write_text(log)
            return dict(half_q=hq,source=source,offset=offset,tco_ns=tco,
                        passed=p.returncode==0 and 'PASS extended SWD' in log)
        matrix=itertools.product([65536,78644,98304,131072,196608],[1,2,3],[-1,0],[8,16,24,32,40,56])
        with ThreadPoolExecutor(max_workers=2) as pool:scan=list(pool.map(point,matrix))
        (sim.OUT/'window_scan.json').write_text(json.dumps(dict(
            fclk_hz=100000000,model='delayed serial target, full read/write/WAIT/FAULT/parity',
            rows=scan),indent=2))
        print('CHARACTERIZATION',len(scan),'points,',sum(r['passed'] for r in scan),'functional passes',flush=True)
    report=dict(rows=rows,all_matched=all(r['matched'] for r in rows),
        production_sha256={str(p.relative_to(ROOT)):sim.hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in rtl.glob('*.v')})
    (sim.OUT/('summary_'+('_'.join(sorted(groups)))+'.json')).write_text(json.dumps(report,indent=2))
    if not report['all_matched']:raise SystemExit(1)

if __name__=='__main__':main()
