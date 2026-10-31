"""Recompute final firmware results, retaining byte/sequence/restore assertions."""
from pathlib import Path
import json
import statistics

root=Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text())
rows=[]
for tr in ['swd','jtag']:
    for speed in [50000,60000]:
        new=load(root/f'sota_final_peak_rtt/peak_{tr}_{speed}.json')
        assert new['passed'] and new['restore_match'] and not new.get('recover_error')
        assert new['artifacts']['elf']['sha256']=='6684400fd217fdd10f4a6375be48eff1e55560d861eca097470a2b88f0a6ddb7'
        old=load(root.parent/f'orbtrace-sota-20261031/historical/peak_{tr}_{speed}.json')
        previous=load(root.parent/f'orbtrace-sota-20261031/optimized/peak_{tr}_{speed}.json')
        assert old['FCLK_Hz']==new['FCLK_Hz']==previous['FCLK_Hz']
        for direction in ['read','write']:
            a,b,c=old[direction]['MB_s'],previous[direction]['MB_s'],new[direction]['MB_s']
            rows.append(dict(metric=f'{tr} {speed//1000}MHz {direction}',historical=a,previous_optimized=b,
                             corrected=c,vs_historical_percent=(c/a-1)*100,vs_previous_percent=(c/b-1)*100))
        new=load(root/f'sota_final_peak_rtt/rtt_{tr}_{speed*1000}.json')
        old=load(root.parent/f'orbtrace-sota-20261031/historical/rtt_{tr}_{speed*1000}.json')
        previous=load(root.parent/f'orbtrace-sota-20261031/optimized/rtt_{tr}_{speed*1000}.json')
        assert new['restore_match']
        assert all(r['sequence_exact'] and r['all_published_received'] and not r['errors'] for r in new['rows'])
        a,b,c=[statistics.median(r['host_MB_s'] for r in d['rows']) for d in [old,previous,new]]
        rows.append(dict(metric=f'{tr} {speed//1000}MHz RTT',historical=a,previous_optimized=b,
                         corrected=c,vs_historical_percent=(c/a-1)*100,vs_previous_percent=(c/b-1)*100))
hss=[]
for path in sorted((root/'sota_final_hss').glob('hss_*_*.json')):
    d=load(path)
    assert d['restore_match']
    for r in d['rows']:
        assert r['all_data_frames_verified'] and r['all_frames_byte_exact'] and r['sample_count_match'] and r['all_frame_sequences_valid']
        assert not r['swd_errors'] and not r['stat_duplicate_frames']
        hss.append({k:r[k] for k in ['speed_hz','period_ticks','variables','repeat','effective_Hz','skip_percent']}
                   |dict(transport='swd' if '_swd_' in path.name else 'jtag'))
assert len(hss)==42
soak=load(root/'sota_final_peak_rtt/peak_swd_60000.json')['soak']
assert soak['elapsed_s']>=30 and soak['errors']==0
for wrapper in ['clock_final_peak_rtt.json','clock_final_hss.json','clock_final50.json']:
    d=load(root/wrapper)
    assert d['returncode']==0 and d['clock_restore_match'] and d['run_halt_restore_match']
for p in (root/'sota_final50').glob('peak_*.json'):
    if p.name=='peak_rtt_runs.json':continue
    d=load(p)
    assert d['passed'] and d['restore_match'] and d['artifacts']['elf']['sha256']=='ad01372c6975fe7af974fd3e7888167239551b9321676aef15c520f7f823e64c'
report=dict(rows=rows,strict_HSS_rows=42,HSS=hss,soak={k:soak[k] for k in ['elapsed_s','iterations','errors','read','write']})
(root/'comparison_final.json').write_text(json.dumps(report,indent=2)+'\n')
table=['| 测项 | 原SOTA本次复测 | 上一优化版 | USB修复版 | 相比上一版 |','| --- | ---: | ---: | ---: | ---: |']
for r in rows:
    table.append(f"| {r['metric']} | {r['historical']:.5f} | {r['previous_optimized']:.5f} | {r['corrected']:.5f} | {r['vs_previous_percent']:+.2f}% |")
(root/'comparison-table.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
print('12 throughput metrics, 42 strict HSS rows, default50 and 30s soak verified.')
