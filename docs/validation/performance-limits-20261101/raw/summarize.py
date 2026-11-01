from pathlib import Path
import hashlib
import json
import statistics

base = Path(__file__).resolve().parent
def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

def summary(folder, transport, speed):
    row = dict(transport=transport, requested_Hz=speed)
    sram = read(folder / f'{transport}-sram-{speed}.json')
    if sram:
        row.update(sram_passed=sram.get('passed'), FCLK_Hz=sram.get('FCLK_Hz'),
                   actual_link_Hz=sram.get('SWCLK_Hz'), restore_match=sram.get('restore_match'))
        for mode in ['read','write']:
            if mode in sram:
                rates=[v['MB_s'] for v in sram[mode]['samples']]
                row[mode+'_MB_s']=sram[mode]['MB_s']
                row[mode+'_range_MB_s']=[min(rates),max(rates)]
        row['soak']= {k:sram.get('soak',{}).get(k) for k in ['elapsed_s','iterations','errors']}
    rtt = read(folder / f'{transport}-rtt-{speed}-etm-original.json')
    if rtt:
        row['rtt_failure']=rtt.get('failure')
        row['rtt_restore_match']=rtt.get('restore_match') and rtt.get('registers_match')
        rows=rtt.get('rows',[])
        row['rtt_verified_runs']=len(rows)
        if rows:
            rates=[v['probe_MB_s'] for v in rows]
            row['rtt_probe_MB_s']=statistics.median(rates)
            row['rtt_probe_range_MB_s']=[min(rates),max(rates)]
            row['rtt_host_MB_s']=statistics.median(v['host_MB_s'] for v in rows)
    hss = read(folder / f'{transport}-hss-{speed}.json')
    if hss:
        for k in ['highest_verified_zero_skip_Hz','zero_period_ticks','zero_verification_runs',
                  'control_sequence_errors','failure','restore_match']:
            row['hss_'+k]=hss.get(k)
        row['hss_all_data_frames_verified']=all(v['all_data_frames_verified'] for v in hss['rows'])
        row['hss_all_sample_counts_match']=all(v['sample_count_match'] for v in hss['rows'])
        row['hss_errors']=sum(v['swd_errors'] for v in hss['rows'])
    return row

result = dict(fixed=[summary(base/'fixed','swd',s) for s in [33333333,66666666]],
              golden=[],release=[],comparisons=[])
for pair in ['golden','release']:
    result[pair]=[summary(base/'ab'/pair,t,s) for t in ['swd','jtag'] for s in [50000000,60000000]]
for g,r in zip(result['golden'],result['release']):
    row=dict(transport=g['transport'],requested_Hz=g['requested_Hz'])
    for k in ['read_MB_s','write_MB_s','rtt_probe_MB_s','hss_highest_verified_zero_skip_Hz']:
        if g.get(k) and r.get(k):
            row[k+'_delta_percent']=100*(r[k]/g[k]-1)
    result['comparisons'].append(row)
(base/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
for pair in ['fixed','golden','release']:
    for r in result[pair]:
        print(pair,r['transport'],r['requested_Hz'],
              'SRAM',r.get('read_MB_s'),r.get('write_MB_s'),
              'RTT',r.get('rtt_probe_MB_s',r.get('rtt_failure')),
              'HSS',r.get('hss_zero_period_ticks'),r.get('hss_highest_verified_zero_skip_Hz'))
for r in result['comparisons']:
    print('DELTA',r)
