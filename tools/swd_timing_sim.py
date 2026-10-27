"""Simulation-only SWD timing verification against the immutable main core.

The reference is extracted from BASELINE, never from a moving branch name.
Instrumentation is generated in build/, not included in production RTL.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'd42b60180e82fccb428c51613a0316776c2bc4fc'
OUT = ROOT / 'build/swd_timing_sim'


def instrument_core(out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    original = subprocess.check_output(
        ['git', 'show', f'{BASELINE}:fpga/rtl/swd_core.v'], cwd=ROOT).decode()
    ref = out / 'swd_core_main.v'
    ref.write_text(original.replace('module swd_core (', 'module swd_core_main (', 1))
    candidate = (ROOT / 'fpga/rtl/swd_core.v').read_text()
    inputs = '''clk rst_n start next_valid next_request next_wdata mode timestamp_en
        idle_cycles data_phase clock_delay delay_fast turn_extra ack_delay
        swj_data swj_count xfer_request xfer_wdata swdio_i swdio_i_fall'''.split()
    outputs = {'next_ready': 1, 'result_valid': 1, 'xfer_rdata': 32,
               'ack': 3, 'parity_err': 1, 'busy': 1, 'timestamp': 16,
               'swclk': 1, 'swdio_o': 1, 'swdio_t': 1}
    monitor = '\n// Generated main-vs-candidate waveform and state miter.\n'
    for name, width in outputs.items():
        monitor += f'wire [{width-1}:0] ref_{name};\n'
    monitor += 'swd_core_main u_main (' + ','.join(
        [f'.{n}({n})' for n in inputs] +
        [f'.{n}(ref_{n})' for n in outputs]) + ');\n'
    monitor += '''integer equivalence_edges = 0;
reg [16:0] equivalence_states = 0;
always @(posedge clk or negedge clk) begin
    #0.001;
    if (rst_n && state < 17) begin
        equivalence_edges = equivalence_edges + 1;
        equivalence_states[state] = 1;
'''
    for name in outputs:
        monitor += (f'        if ({name} !== ref_{name}) '
                    f'$fatal(1,"MAIN_MISMATCH {name} t=%0t state=%0d lsm=%0d got=%h ref=%h",'
                    f'$time,state,lsm_cnt,{name},ref_{name});\n')
    # Also compare registered sample contents and protocol progress. This catches
    # a one-cycle sample shift even if a particular payload masks it at the pins.
    for name in ['state', 'lsm_cnt', 'ack_samples', 'rd_samples', 'active_request',
                 'wr_shift', 'idle_cnt', 'turn_wait', 'ack_hold', 'rd_data_parity']:
        monitor += (f'        if ({name} !== u_main.{name}) '
                    f'$fatal(1,"MAIN_MISMATCH {name} t=%0t state=%0d lsm=%0d",'
                    '$time,state,lsm_cnt);\n')
    monitor += '''    end
end
final $display("MAIN_EQUIVALENCE edges=%0d states=%h",equivalence_edges,equivalence_states);
'''
    instrumented = out / 'swd_core_checked.v'
    instrumented.write_text(candidate.rsplit('endmodule', 1)[0] + monitor + '\nendmodule\n')
    return [instrumented, ref, ROOT / 'fpga/rtl/swj_clk_gen.v']


def compile_top(top, sources, name, params=None):
    exe = OUT / (name + '.vvp')
    command = ['iverilog', '-g2012', '-s', top, '-o', str(exe)]
    for key, value in (params or {}).items():
        command += ['-P', f'{top}.{key}={value}']
    # Keep diagnostics readable and avoid unnecessarily long worktree filenames.
    command += [str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
                for p in sources]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (OUT / (name + '.compile.log')).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return exe


def simulate(exe, name, args=(), timeout=120, expect_pass=True, pass_marker='PASS'):
    start = time.monotonic()
    result = subprocess.run(['vvp', str(exe), *args], cwd=OUT,
                            capture_output=True, text=True, timeout=timeout)
    log = result.stdout + result.stderr
    (OUT / (name + '.log')).write_text(log)
    passed = result.returncode == 0 and pass_marker in log
    matched = passed == expect_pass and 'MAIN_MISMATCH' not in log
    row = dict(name=name, passed=passed, expected_pass=expect_pass,
               matched=matched, seconds=round(time.monotonic()-start, 3),
               equivalence=re.findall(r'MAIN_EQUIVALENCE edges=(\d+) states=(\w+)', log),
               budget=[dict(zip(['words','read','idle','half_ns','cycles','rises','launches'],
                                map(int, m))) for m in re.findall(
                   r'BUDGET words=(\d+) read=(\d+) idle=(\d+) half_ns=(\d+) cycles=(\d+) rises=(\d+) launches=(\d+)', log)])
    print(f'{"PASS" if matched else "FAIL"} {name} ({row["seconds"]}s)', flush=True)
    if not matched:
        print(log[-2500:], flush=True)
    return row


def compile_xsim(sources):
    """Use the installed second simulator for the real ARM gate-level model.

    Windows Icarus 11 asserts in StringHeap's realloc-shrink assumption on this
    design. Do not edit or simplify the licensed target to work around it.
    """
    import run_cortexm0_sim as xs
    env, paths = xs.environment()
    work = OUT/'xsim'
    work.mkdir(exist_ok=True)
    xs.WORK = work
    xs.SNAPSHOT = 'swd_timing'
    sv=[p for p in sources if p.suffix=='.sv' or p.name=='swd_core_checked.v']
    verilog=[p for p in sources if p not in sv]
    for name, command in [
        ('xvlog_v',['xvlog.exe','--relax',*map(str,verilog)]),
        ('xvlog_sv',['xvlog.exe','--relax','--sv',*map(str,sv)]),
        ('xelab',['xelab.exe','--debug','typical','--snapshot',xs.SNAPSHOT,
                  'tb_cortexm0_link'])]:
        command[0]=str(xs.VIVADO/'bin/unwrapped/win64.o'/command[0])
        p=subprocess.run(command,cwd=work,env=env,capture_output=True,text=True,
                         errors='replace',timeout=300)
        log=p.stdout+p.stderr;(work/(name+'.console.log')).write_text(log)
        if p.returncode:
            raise RuntimeError(log[-5000:])
    xs.prepare_kernel(paths)
    return work,env


def simulate_xsim(work,env,name,args,timeout=900,expected_ack=None):
    import run_cortexm0_sim as xs
    command=[str(xs.VIVADO/'bin/unwrapped/win64.o/xsim.exe'),
             'swd_timing','--runall','--log',str(OUT/(name+'.xsim.log'))]
    for arg in args:
        command+=['--testplusarg',arg.lstrip('+')]
    start=time.monotonic()
    p=subprocess.run(command,cwd=work,env=env,capture_output=True,text=True,
                     errors='replace',timeout=timeout)
    log=p.stdout+p.stderr;(OUT/(name+'.log')).write_text(log)
    passed=p.returncode==0 and 'PASS CortexM0' in log and not re.search(
        r'Fatal:|FATAL|MAIN_MISMATCH',log)
    if '+services' in args:
        passed=passed and 'SERVICES_PASS' in log
    expected_rejection=expected_ack is not None
    rejected_as_expected=expected_rejection and not passed and 'MAIN_MISMATCH' not in log and (
        f'Fatal: transfer req=02 ACK={expected_ack}' in log)
    row=dict(name=name,passed=bool(passed),matched=bool(passed) if not expected_rejection else bool(rejected_as_expected),simulator='XSim',
             args=list(args),
             expected_pass=not expected_rejection,expected_ack=expected_ack,
             seconds=round(time.monotonic()-start,3),
             equivalence=re.findall(r'MAIN_EQUIVALENCE edges=(\d+) states=(\w+)',log),
             fault_model_skip='FAULT_SKIP' in log)
    print(f'{"PASS" if row["matched"] else "FAIL"} {name}'+
          (' (expected rejection)' if expected_rejection else '')+f' ({row["seconds"]}s)',flush=True)
    if not row['matched']:print(log[-4000:],flush=True)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--groups', default='unit,control,wave,wire,budget,packet,probe,m0,baseline,host')
    ap.add_argument('--m0-only',default='',help='Comma-separated M0 case filters; merge results for unchanged RTL')
    args = ap.parse_args()
    checked = instrument_core()
    groups = {'wire'} if args.quick else set(args.groups.split(','))
    known_groups={'unit','control','wave','wire','budget','packet','probe','m0','baseline','host'}
    if groups-known_groups:
        ap.error('Unknown groups: '+','.join(sorted(groups-known_groups)))
    if args.m0_only and groups!={'m0'}:
        ap.error('--m0-only requires --groups m0')
    rows = []
    sim = ROOT/'fpga/sim'
    rtl = ROOT/'fpga/rtl'
    controller = [rtl/f for f in ['swd_controller.v','swd_batch_engine.v',
        'dap_transfer_block_engine.v','probe_sample_engine.v','probe_rtt_engine.v',
        'probe_stream_engine.v']] + [sim/'sim_primitives.v',sim/'xpm_memory_tdpram.sv']

    def run(top, name, extra=(), params=None, plusargs=(), timeout=180,
            expect_pass=True, core=True, pass_marker='PASS'):
        files = (checked if core else []) + list(extra) + [sim/(top+'.sv')]
        actual_top=re.search(r'module\s+(\w+)',(sim/(top+'.sv')).read_text())[1]
        exe = compile_top(actual_top, files, name, params)
        rows.append(simulate(exe,name,plusargs,timeout,expect_pass,pass_marker))

    if 'unit' in groups:
        run('tb_swj_clk_gen','generator',extra=[rtl/'swj_clk_gen.v'],core=False)
    if 'control' in groups:
        run('tb_swd_timing_equiv','control',timeout=1200)
    if 'wave' in groups:
        run('tb_swd_timing_equiv','wave_example',plusargs=['+wave'])
    if 'wire' in groups:
        for phase,tco in [(0,16)]:
            run('tb_swd_stream',f'wire_p{phase}_t{tco}',
                [rtl/'swd_batch_engine.v',sim/'xpm_memory_tdpram.sv'],
                {'SAMPLE_RISE':phase,'TCO_NS':tco})
        for tco,hold,ack in [(16,0,1),(16,0,2),(40,0,2),(40,2,2)]:
            run('tb_swd_ack_delay',f'ack_t{tco}_h{hold}_a{ack}',params={
                'TARGET_TCO_NS':tco,'ACK_DELAY':hold,'EXPECT_ACK':ack},
                expect_pass=not(tco==40 and hold==0))
    if 'budget' in groups:
        baseline_core=OUT/'swd_core_baseline.v'
        baseline_core.write_text(checked[1].read_text().replace(
            'module swd_core_main (','module swd_core (',1))
        for mhz,half_ns,idle in [(50,5.0,0),(50,5.0,1),(50,5.0,2),
                                (60,4.166667,1),(60,4.166667,2)]:
            name=f'budget_{mhz}_idle{idle}'
            params={'IDLE_CYCLES':idle,'CLK_HALF_NS':half_ns}
            run('tb_packet_wire_budget',name,[rtl/'dap_transfer_block_engine.v'],params)
            candidate=rows[-1]
            ref_exe=compile_top('tb_packet_wire_budget',[baseline_core,
                rtl/'dap_transfer_block_engine.v',sim/'tb_packet_wire_budget.sv'],
                name+'_main',params)
            reference=simulate(ref_exe,name+'_main')
            rows.append(reference)
            identical=candidate['budget']==reference['budget']
            candidate.update(budget_matches_main=identical,SWCLK_MHz=mhz)
            candidate['matched']=candidate['matched'] and identical
    if 'packet' in groups:
        for top in ['tb_dap_transfer_block_engine','tb_engine_cases',
                    'tb_engine_retry','tb_engine_lat1','tb_packet_contract']:
            run(top,top,[rtl/'dap_transfer_block_engine.v'],core=False,
                pass_marker='PASS')
        # This older AXI ownership test deliberately forces core outputs. It
        # tests the wrapper/mux, not waveform equivalence. Real serial service
        # tests below run with the miter and no forced transaction results.
        run('tb_packet_axi','packet_axi',[rtl/'swd_core.v',rtl/'swj_clk_gen.v']+
            [p for p in controller if p.name!='sim_primitives.v'],core=False)
        run('tb_batch_dma','batch_dma',[rtl/'swd_batch_engine.v',
                                      sim/'xpm_memory_tdpram.sv'],core=False)
    if 'probe' in groups:
        run('tb_probe_sample','probe_sample',[rtl/'probe_sample_engine.v'],core=False)
        run('tb_probe_sample_pipe','probe_pipe',[rtl/'probe_sample_engine.v',
            sim/'probe_ap_model.sv'],core=False)
        run('tb_probe_stream_dma','probe_stream_dma',[rtl/'probe_stream_engine.v',
            rtl/'probe_rtt_engine.v',sim/'probe_ap_model.sv',
            sim/'xpm_memory_tdpram.sv'],core=False)
    if 'm0' in groups:
        from run_cortexm0_regress import DEFAULT_MODEL, MODEL, MATRIX
        work,env=compile_xsim(checked+controller+
            [DEFAULT_MODEL/f for f in MODEL]+[sim/'tb_cortexm0_link.sv'])
        cases=MATRIX+[
            ('recovery',['+recovery','+idle=1']),
            ('idle1',['+idle=1','+packets']),('idle2',['+idle=2','+packets']),
            ('swd50',['+half_ns=5.0','+idle=1','+packets']),
            ('services',['+services','+idle=1'])]
        for name,plusargs in cases:
            if not args.m0_only or any(token in name for token in args.m0_only.split(',')):
                # These default-phase windows also fail on frozen main alone;
                # keep them as explicit rejection tests, not functional passes.
                expected_ack={'ret8':'4','ret30':'3','ret50':'7'}.get(name)
                rows.append(simulate_xsim(work,env,'m0_'+name,plusargs,
                                         expected_ack=expected_ack))
    if 'baseline' in groups:
        from run_cortexm0_regress import DEFAULT_MODEL, MODEL
        baseline_core=OUT/'swd_core_baseline.v'
        baseline_core.write_text(checked[1].read_text().replace(
            'module swd_core_main (','module swd_core (',1))
        work,env=compile_xsim([baseline_core]+controller+
            [DEFAULT_MODEL/f for f in MODEL]+[sim/'tb_cortexm0_link.sv'])
        for ns,ack in [(8,'4'),(30,'3'),(50,'7')]:
            rows.append(simulate_xsim(work,env,'main_ret'+str(ns),
                        [f'+return_ns={ns}.0','+packets'],expected_ack=ack))
    if 'host' in groups:
        for script in ['test_probe_host.py','test_dap_transport.py']:
            command=['python',str(ROOT/'tools'/script)]
            if script=='test_dap_transport.py' and os.name=='nt' and shutil.which('clang'):
                command+=['--cc','clang']
            p=subprocess.run(command,cwd=ROOT,
                             capture_output=True,text=True,timeout=180)
            log=p.stdout+p.stderr;(OUT/(script+'.log')).write_text(log)
            ok=p.returncode==0 and 'PASS' in log
            rows.append(dict(name=script,matched=ok,passed=ok))
            print(f'{"PASS" if ok else "FAIL"} {script}',flush=True)
    report = dict(baseline=BASELINE, rows=rows,
                  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (ROOT/'fpga/rtl').glob('*.v')})
    dest=OUT/('summary_'+('_'.join(sorted(groups)))+'.json')
    if args.m0_only and dest.exists():
        previous=json.loads(dest.read_text())
        if previous['source_sha256']==report['source_sha256']:
            known={'m0_'+name for name,_ in cases}
            merged={r['name']:r for r in previous['rows'] if r['name'] in known}
            merged.update({r['name']:r for r in rows})
            report['rows']=list(merged.values())
    dest.write_text(json.dumps(report, indent=2))
    if not rows or not all(r['matched'] for r in report['rows']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
