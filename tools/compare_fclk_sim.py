"""Golden/candidate transport gate using identical CM3 benches and model.

No board operations. The Golden DUT is exported by immutable Git revision;
the current benches are deliberately shared by both runs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--golden',default='954de8fd09f4a97aafb7dc42fa5e4a9a019c3f19')
    p.add_argument('--phase',choices=['golden','candidate','compare'],required=True)
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    revision=subprocess.check_output(['git','rev-parse',a.golden],cwd=ROOT,text=True).strip()
    golden=out/'golden-rtl';golden.mkdir(exist_ok=True)
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'fpga/rtl'],cwd=ROOT,text=True).splitlines()
    for name in names:
        if name.endswith('.v'):
            data=subprocess.check_output(['git','show',f'{revision}:{name}'],cwd=ROOT)
            target=golden/Path(name).name
            if not target.exists() or target.read_bytes()!=data:target.write_bytes(data)
    if a.phase!='compare':
        dut=golden if a.phase=='golden' else ROOT/'fpga/rtl'
        report={'golden_revision':revision,'hardware_access':False,'FCLK_Hz':120000000,
                'external_debug_Hz':60000000,'target_HCLK_Hz':100000000,'phase':a.phase,
                'hss_minimum_period_ticks':24,'hss_maximum_requested_Hz':1000000,
                'model_manifest_sha256':hashlib.sha256((ROOT/'docs/cm3-model.json').read_bytes()).hexdigest(),
                'sources':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(dut.glob('*.v'))},
                'benches':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'fpga/sim').glob('*')) if f.is_file()},
                'cases':[]}
        for top,args in [('tb_cm3_swd',['half_ns=4.166667','rx_boundary=0','return_ns=16','target_clk_ns=10','benchmark']),
                         ('tb_cm3_jtag',['clk_ns=8.333333','target_clk_ns=10','benchmark'])]:
            work=out/a.phase/top
            cmd=[sys.executable,str(ROOT/'tools/run_cm3_sim.py'),'--top',top,'--dut-rtl',str(dut),'--work-dir',str(work),*args]
            r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,errors='replace')
            work.mkdir(parents=True,exist_ok=True)
            (work/'runner.txt').write_text(r.stdout+r.stderr,encoding='utf8')
            log=(work/'xsim.log').read_text(encoding='utf8',errors='replace') if (work/'xsim.log').exists() else r.stdout+r.stderr
            metrics=[]
            for line in log.splitlines():
                if line.startswith(('SIM_SRAM ','SIM_RTT ','SIM_HSS ')):
                    row={'kind':line.split()[0]}
                    row.update({k:float(v) for k,v in re.findall(r'(\w+)=([\d.eE+-]+)',line)})
                    if 'elapsed_ns' in row:row['fclk_cycles']=round(row['elapsed_ns']/(1e9/120000000))
                    metrics.append(row);print(top,line,flush=True)
            passed=r.returncode==0 and 'PASS SIM_TRANSPORT_BENCH' in log and len(metrics)==5
            if any(hashlib.sha256(f.read_bytes()).hexdigest()!=report['sources'][f.name] for f in dut.glob('*.v')):
                raise RuntimeError('DUT sources changed during simulation')
            if any(hashlib.sha256(f.read_bytes()).hexdigest()!=report['benches'][f.name] for f in (ROOT/'fpga/sim').glob('*') if f.is_file()):
                raise RuntimeError('Benches changed during simulation')
            report['cases'].append({'top':top,'passed':passed,'arguments':args,'metrics':metrics})
            (out/(a.phase+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
            print(a.phase,top,'PASS' if passed else 'FAIL',flush=True)
            if not passed:print((r.stdout+r.stderr)[-3000:]);return 1
        return 0
    base=json.loads((out/'golden.json').read_text());current=json.loads((out/'candidate.json').read_text())
    expected_tops=['tb_cm3_swd','tb_cm3_jtag']
    if [c['top'] for c in base['cases']]!=expected_tops or [c['top'] for c in current['cases']]!=expected_tops:
        raise RuntimeError('Incomplete SWD/JTAG matrix; synthesis gate remains closed')
    if base['benches']!=current['benches']:raise RuntimeError('Golden/candidate benches changed; rerun both')
    if current['sources']!={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'fpga/rtl').glob('*.v')}:
        raise RuntimeError('Candidate RTL differs from tested source; rerun candidate')
    if current['benches']!={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'fpga/sim').glob('*') if f.is_file()}:
        raise RuntimeError('Current benches differ from comparison; rerun both')
    checks=[]
    for b,c in zip(base['cases'],current['cases'],strict=True):
        if b['top']!=c['top'] or not b['passed'] or not c['passed'] or len(b['metrics'])!=5 or len(c['metrics'])!=5:raise RuntimeError('Incomplete or mismatched run')
        for bm,cm in zip(b['metrics'],c['metrics'],strict=True):
            if bm['kind']!=cm['kind'] or bm.get('read')!=cm.get('read'):raise RuntimeError('Metric mismatch')
            key='Hz' if bm['kind']=='SIM_HSS' else 'MBps'
            passed=cm[key]>=bm[key]-0.000001
            if bm['kind']=='SIM_HSS':
                passed &= cm['period']==bm['period'] and cm['skip_percent']<=bm['skip_percent']+0.000001
                if bm['skipped']==0:passed &= cm['skipped']==0
            checks.append({'top':b['top'],'kind':bm['kind'],'golden':bm,'candidate':cm,'passed':passed})
    result={'passed':all(x['passed'] for x in checks),'hardware_access':False,'checks':checks}
    (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
