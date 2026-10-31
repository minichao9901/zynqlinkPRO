"""Rebuild SOTA comparison from the retained raw measurements."""
from pathlib import Path
import json
import statistics

root=Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text())
rows=[]
for tr in ['swd','jtag']:
    for speed in [50000,60000]:
        old=load(root/f'historical/peak_{tr}_{speed}.json')
        new=load(root/f'optimized/peak_{tr}_{speed}.json')
        assert old['passed'] and new['passed'] and old['restore_match'] and new['restore_match']
        assert old['FCLK_Hz']==new['FCLK_Hz'] and old['SWCLK_Hz']==new['SWCLK_Hz']
        for direction in ['read','write']:
            a,b=old[direction]['MB_s'],new[direction]['MB_s']
            rows.append(dict(metric=f'{tr.upper()} {speed//1000}MHz {direction}',
                historical_rerun=a,optimized=b,percent=(b/a-1)*100,FCLK_Hz=new['FCLK_Hz'],actual_link_Hz=new['SWCLK_Hz']))
        old=load(root/f'historical/rtt_{tr}_{speed*1000}.json')
        new=load(root/f'optimized/rtt_{tr}_{speed*1000}.json')
        for report in [old,new]:
            assert report['restore_match']
            assert all(r['sequence_exact'] and r['all_published_received'] and not r['errors'] for r in report['rows'])
        a,b=[statistics.median(r['host_MB_s'] for r in report['rows']) for report in [old,new]]
        rows.append(dict(metric=f'{tr.upper()} {speed//1000}MHz RTT',historical_rerun=a,optimized=b,percent=(b/a-1)*100))
hss=[]
for path in sorted((root/'optimized').glob('hss_*_*.json')):
    report=load(path)
    if 'rows' not in report: continue
    assert report['restore_match']
    for row in report['rows']:
        assert row['all_data_frames_verified'] and row['sample_count_match'] and row['all_frame_sequences_valid']
        assert row['all_frames_byte_exact'] and not row['swd_errors'] and not row['stat_duplicate_frames']
        hss.append({k:row[k] for k in ['speed_hz','variables','period_ticks','repeat','effective_Hz','skip_percent']}
                   |dict(transport='swd' if '_swd_' in path.name else 'jtag'))
out=dict(comparison=rows,strict_hss_rows=len(hss),hss=hss,
    scope='96MHz temporary clock/RAM fixtures; no target Flash writes; old probe pair reloaded for peak and RTT, historical HSS table not rerun')
(root/'comparison.json').write_text(json.dumps(out,indent=2)+'\n')
table=['| 测项 | 旧配对本次复测 MB/s | 优化版 MB/s | 变化 |','| --- | ---: | ---: | ---: |']
for row in rows:
    table.append(f"| {row['metric']} | {row['historical_rerun']:.5f} | {row['optimized']:.5f} | {row['percent']:+.2f}% |")
(root/'comparison-table.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
print('\n'.join(table));print('Strict HSS rows:',len(hss))
