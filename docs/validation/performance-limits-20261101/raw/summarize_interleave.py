from pathlib import Path
import json

base = Path(__file__).resolve().parent
root = base/'interleave'
reports = {}
for name in ['release-swd-final','release-jtag','golden-swd','golden-jtag','fixed-swd']:
    path=root/name/'result.json'
    if not path.exists():continue
    d=json.loads(path.read_text())
    rows=[]
    for r in d['rows']:
        v={k:r.get(k) for k in ['service','speed_hz','variables','passed','error','session_bytes',
            'session_samples','DAP_yields','skipped','timer_rebase_events','sample_timestamps_monotonic',
            'stat_duplicate_frames','first_DEF_verified']}
        debug=r.get('debug',{})
        v.update(bursts=debug.get('bursts'),DAP_requests_in_bursts=debug.get('dap_requests_in_bursts'),
                 halt_step_resume_runs=len(debug.get('halt_step_resume',[])),
                 max_debug_burst_ms=1000*debug.get('max_debug_burst_s',0),
                 post_debug_progress=debug.get('post_debug_progress'))
        stages=debug.get('stage_counters',[])
        v['windows']=[]
        for a,b in zip(stages,stages[1:]):
            w=dict(stage=b['stage'],host_received=b['received']-a['received'])
            if r['service']=='hss':
                dt=((b['metrics'][1]-a['metrics'][1])&0xffffffff)/24e6
                n=(b['metrics'][3]-a['metrics'][3])&0xffffffff
                w.update(seconds=dt,produced=n,effective_Hz=n/dt,
                         skipped=(b['metrics'][4]-a['metrics'][4])&0xffffffff)
            v['windows'].append(w)
        rows.append(v)
    reports[name]=dict(passed=d.get('passed'),failure=d.get('failure'),
        restore_match=d.get('restore_match'),registers_match=d.get('registers_match'),
        run_halt_restored=d.get('run_halt_restored'),rows=rows,
        acceptanceScope='DAP responsiveness, stream continuity and payload; HSS sample timing assessed separately')
    for r in rows:
        print(name,r['service'],r['speed_hz'],r['variables'],r['passed'],r['bursts'],
              r['max_debug_burst_ms'],r['halt_step_resume_runs'])
(base/'interleave-summary.json').write_text(json.dumps(reports,indent=2)+'\n')
