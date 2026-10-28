"""Reproducible main/short-return SWD boundary regressions using XSim.

Licensed ARM target sources are read in place. Legacy runs compare every core
pin, result, state and shift register against immutable main d42b601 at both
FCLK edges. Source hashes, simulator logs and results are retained per run.
"""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,time
import run_cortexm0_sim as xs
from run_cortexm0_regress import DEFAULT_MODEL,MODEL
ROOT=Path(__file__).resolve().parents[1]
BASE='d42b60180e82fccb428c51613a0316776c2bc4fc'

def checked_core(out):
    original=subprocess.check_output(['git','show',f'{BASE}:fpga/rtl/swd_core.v'],cwd=ROOT).decode()
    ref=out/'swd_core_main.v';ref.write_text(original.replace('module swd_core (','module swd_core_main (',1))
    src=(ROOT/'fpga/rtl/swd_core.v').read_text()
    inputs='clk rst_n start next_valid next_request next_wdata mode timestamp_en idle_cycles data_phase clock_delay delay_fast turn_extra ack_delay swj_data swj_count xfer_request xfer_wdata swdio_i swdio_i_fall'.split()
    outputs=dict(next_ready=1,result_valid=1,xfer_rdata=32,ack=3,parity_err=1,busy=1,timestamp=16,swclk=1,swdio_o=1,swdio_t=1)
    code='\n'+''.join(f'wire [{w-1}:0] ref_{n};\n' for n,w in outputs.items())
    code+='swd_core_main u_main ('+','.join([f'.{n}({n})' for n in inputs]+[f'.{n}(ref_{n})' for n in outputs])+');\n'
    code+='''integer equivalent_edges=0;
always @(posedge clk or negedge clk) begin
 #0.001;
 if(rst_n && !rx_boundary) begin
  equivalent_edges=equivalent_edges+1;
'''
    for n in outputs:
        code+=f'if({n} !== ref_{n}) $fatal(1,"MAIN_MISMATCH {n} t=%0t",$time);\n'
    for n in 'state lsm_cnt delay_cnt ack_samples rd_samples active_request wr_shift idle_cnt turn_wait ack_hold rd_data_parity'.split():
        code+=f'if({n} !== u_main.{n}) $fatal(1,"MAIN_MISMATCH {n} t=%0t",$time);\n'
    code+='end\nend\nfinal $display("MAIN_EQUIVALENCE edges=%0d",equivalent_edges);\n'
    code+='''integer accepted_at=0,wire_cycle=0;
always @(posedge clk) begin
 wire_cycle=wire_cycle+1;
 if(result_valid) $display("CORE_CYCLES read=%b cycles=%0d",is_read_op,wire_cycle-accepted_at);
 if((state==ST_IDLE && start && mode) || (next_valid && next_ready)) accepted_at=wire_cycle;

end
'''
    dest=out/'swd_core_checked.sv';dest.write_text(src.rsplit('endmodule',1)[0]+code+'\nendmodule\n')
    return [dest,ref]

def build(out,model):
    sources=[p for p in (ROOT/'fpga/rtl').glob('*.v') if p.name!='swd_core.v']+checked_core(out)
    sources += [ROOT/'fpga/sim'/f for f in ['sim_primitives.v','xpm_memory_tdpram.sv','tb_cortexm0_link.sv']]+[model/f for f in MODEL]
    (out/'sources.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sources,ROOT/'fpga/rtl/swd_core.v']},indent=2))
    work=out/'xsim';work.mkdir(exist_ok=True);xs.WORK=work;xs.SNAPSHOT='swd_rx'
    env,paths=xs.environment()
    for exe,args in [('xvlog.exe',['--relax',*[str(p) for p in sources if p.suffix!='.sv']]),('xvlog.exe',['--relax','--sv',*[str(p) for p in sources if p.suffix=='.sv']]),('xelab.exe',['--debug','typical','--snapshot',xs.SNAPSHOT,'tb_cortexm0_link'])]:
        p=subprocess.run([str(xs.VIVADO/'bin/unwrapped/win64.o'/exe),*args],cwd=work,env=env,capture_output=True,text=True,errors='replace',timeout=300)
        (out/(exe+('_sv' if '--sv' in args else '')+'.log')).write_text(p.stdout+p.stderr)
        if p.returncode: raise RuntimeError((p.stdout+p.stderr)[-4000:])
    xs.prepare_kernel(paths)
    return work,env

def matrix(suite):
    cases=[]
    def add(name,half,rx,phase,ret=16,extra=(),expected=True):
        cases.append((name,[f'half_ns={half}',f'rx_boundary={rx}',f'phase={phase}',f'return_ns={ret}','words=2','idle=1',*extra],expected))
    if suite=='policy':
        add('policy30_ret20',8.333333,1,0,20,extra=['errors','streams'])
        add('policy35_ret20',7.222222,0,1,20,extra=['errors','streams'])
        add('policy45_ret20',5.555556,0,1,20,extra=['errors','streams'])
    if suite=='trace':
        add('trace_25MHz',10,1,0,extra=['raw_trace'])
        add('legacy50_trace_off',5,0,0)
    if suite=='smoke':
        add('legacy_50MHz',5,0,0)
        add('rx_25MHz',10,1,1,extra=['errors','streams'])
        add('rx_10MHz',25,1,1,extra=['errors'])
        add('rx_5MHz',50,1,1,extra=['errors'])
    if suite=='boundary':
        add('firmware_35MHz',7.142857,1,0,extra=['packets','streams','errors','recovery'])
        add('rx_zero_idle',10,1,0,extra=['idle=0','packets','errors'])
        add('rx_delay1',5,1,0,4,extra=['transfer_delay=1','errors'])
        add('rx_delay3',5,1,0,4,extra=['transfer_delay=3','errors'])
    if suite=='sweep':
        for half in [5,6.25,7.142857,8.333333,10,25,50]:
            for phase in [0,1]: add(f'rx_h{half}_q{phase}',half,1,phase,expected=16 < half*(2 if phase else 3))
        for ret in [0,4,8,12,24,32]: add(f'rx_10MHz_ret{ret}',25,1,1,ret,extra=['errors'])
        add('legacy_25MHz_failure',10,0,1,expected=False)
        add('rx_1MHz',250,1,1,extra=['errors'])
        add('rx_250kHz',1000,1,1)
    if suite=='full':
        for name,half,rx,phase in [('legacy50',5,0,0),('rx25',10,1,1),('rx10',25,1,1)]:
            add(name+'_all',half,rx,phase,extra=['packets','errors','streams','recovery'])
        add('legacy_sampler',5,0,0,extra=['sampler'])
        add('rx_sampler',10,1,1,extra=['sampler'])
        for delay in [1,3,7]: add(f'legacy_ack{delay}',5,0,0,extra=[f'ack_delay={delay}'])
        for turn in [1,2,3]: add(f'rx_turn{turn}',10,1,1,extra=[f'turn_extra={turn}','errors'])
    return cases

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--suite',choices=['smoke','sweep','full','boundary','trace','policy'],default='smoke')
    ap.add_argument('--out',default='build/swd_rx_smoke');ap.add_argument('--model-dir',type=Path,default=DEFAULT_MODEL)
    ap.add_argument('--reuse',action='store_true');ap.add_argument('--only',default='');a=ap.parse_args()
    out=(ROOT/a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    if a.reuse:
        sources=json.loads((out/'sources.json').read_text())
        for f,h in sources.items():
            if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h: raise SystemExit('Source changed: '+f)
        env,_=xs.environment();work=out/'xsim'
    else: work,env=build(out,a.model_dir)
    rows=[]
    for name,args,expected in matrix(a.suite):
        if a.only and a.only not in name:continue
        t=time.monotonic()
        cmd=[str(xs.VIVADO/'bin/unwrapped/win64.o/xsim.exe'),'swd_rx','-runall','-log',str(out/(name+'.xsim.log'))]
        for arg in args:cmd+=['-testplusarg',arg]
        p=subprocess.run(cmd,cwd=work,env=env,capture_output=True,text=True,errors='replace',timeout=900)
        log=p.stdout+p.stderr;(out/(name+'.log')).write_text(log)
        passed=p.returncode==0 and 'PASS CortexM0' in log and not re.search('Fatal:|MAIN_MISMATCH',log)
        # An expected failure must be the original ACK/DPIDR alignment failure.
        matched=passed if expected else not passed and ('transfer req=02 ACK=' in log or 'DPIDR ' in log)
        row=dict(name=name,args=args,passed=passed,expected=expected,matched=matched,seconds=round(time.monotonic()-t,2),equivalent_edges=re.findall(r'MAIN_EQUIVALENCE edges=(\d+)',log),cycles=sorted(set(re.findall(r'CORE_CYCLES read=(\d) cycles=(\d+)',log))),markers=[l for l in log.splitlines() if '_PASS' in l or 'FAULT_SKIP' in l or 'Fatal:' in l])
        rows.append(row);(out/(a.suite+'_summary.json')).write_text(json.dumps(rows,indent=2))
        print(('EXPECTED_FAIL' if matched and not expected else ('PASS' if matched else 'FAIL'))+' '+name+' '+str(row['seconds'])+'s',flush=True)
        if not matched: print(log[-1800:],flush=True)
    if any(not r['matched'] for r in rows):raise SystemExit(1)
if __name__=='__main__':main()
