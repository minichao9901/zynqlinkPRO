"""Rebuild the read-only hardware comparison from committed raw JSON files."""
import collections
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent


def read(profile, name):
    return json.loads((ROOT / profile / name).read_text(encoding='utf-8-sig'))


def median_rows(value, key, **where):
    rows = [r for r in value['rows'] if all(r.get(k) == v for k, v in where.items())]
    assert rows and all(r.get('passed') is not False for r in rows)
    return statistics.median(r[key] for r in rows)


metrics = []


def compare(name, old, new, unit, old_file, new_file):
    row = dict(name=name, baseline=old, optimized=new, unit=unit,
               delta_percent=100 * (new / old - 1), baseline_file=old_file,
               optimized_file=new_file)
    metrics.append(row)
    return row


b = read('recent_filtered_baseline', 'swd_cmsis_depth16.json')
c = read('optimized_50_final', 'cmsis_depth16.json')
for field, label in [('read_MB_s', 'SWD 50MHz 20KiB linear read, depth16'),
                     ('write_MB_s', 'SWD 50MHz 20KiB linear write, depth16')]:
    compare(label, b[field], c[field], 'MB/s', 'recent_filtered_baseline/swd_cmsis_depth16.json',
            'optimized_50_final/cmsis_depth16.json')

b = read('recent_filtered_baseline', 'jtag_sram_long.json')['rows'][0]
c = read('optimized_pl_same_ps_control', 'jtag_sram_long.json')['rows'][0]
assert b['FCLK_Hz'] == c['FCLK_Hz'] and b['cfg'] == c['cfg']
for field in ['read_seq', 'read_pipe', 'write_pipe']:
    compare('JTAG 50MHz 1KiB ' + field + ', 5x2s', b[field]['MB_s'], c[field]['MB_s'],
            'MB/s', 'recent_filtered_baseline/jtag_sram_long.json',
            'optimized_pl_same_ps_control/jtag_sram_long.json')

for transport, old_file, new_file, speeds in [
    ('SWD', 'swd_35_50_long_rtt.json', 'rtt_long_swd.json', [35000000, 50000000]),
    ('JTAG', 'rtt_long_jtag.json', 'rtt_long_jtag.json', [50000000]),
]:
    b = read('recent_filtered_baseline', old_file)
    c = read('optimized_50_final', new_file)
    assert b['restore_match'] and c['restore_match']
    for speed in speeds:
        for field in ['host_MB_s', 'probe_MB_s']:
            compare(f'{transport} request {speed}Hz RTT {field}, 3x8s',
                    median_rows(b, field, speed_hz=speed), median_rows(c, field, speed_hz=speed),
                    'MB/s', 'recent_filtered_baseline/' + old_file,
                    'optimized_50_final/' + new_file)

control = []
b = read('baseline_pl_final_ps_control', 'hss_overload_swd.json')
c = read('optimized_pl_same_ps_control', 'hss_overload_swd.json')
for period in [240, 200, 192]:
    row = dict(period_ticks=period, nominal_requested_Hz=24000000 / period,
               baseline_pl_Hz=median_rows(b, 'effective_Hz', period_ticks=period),
               optimized_pl_Hz=median_rows(c, 'effective_Hz', period_ticks=period),
               baseline_skip_percent=median_rows(b, 'skip_percent', period_ticks=period),
               optimized_skip_percent=median_rows(c, 'skip_percent', period_ticks=period))
    row['delta_percent'] = 100 * (row['optimized_pl_Hz'] / row['baseline_pl_Hz'] - 1)
    row['same_elf_sha256'] = b['artifacts']['elf']['sha256']
    assert row['same_elf_sha256'] == c['artifacts']['elf']['sha256']
    for value, prefix in [(b, 'baseline'), (c, 'optimized')]:
        selected = [r for r in value['rows'] if r['period_ticks'] == period]
        assert len(selected) == 5 and all(r['sample_count_match'] and
                                         r['all_frame_sequences_valid'] for r in selected)
        row[prefix + '_packets_per_sample'] = (sum(r['data_frames_verified'] for r in selected) /
                                               sum(r['session_received_samples'] for r in selected))
    control.append(row)

frontier = []
for profile, filename in [('recent_filtered_baseline', 'swd_25_fixed_frontier.json'),
                           ('optimized_50_final', 'hss_swd_25000000.json')]:
    v = read(profile, filename)
    selected = [r for r in v['rows'] if r['period_ticks'] == 47]
    assert len(selected) == 3 and all(r['passed'] and r['skipped'] == 0 for r in selected)
    frontier.append(dict(profile=profile, actual_link_Hz=selected[0]['actual_link_Hz'],
                         period_ticks=47, verified_Hz=24000000 / 47, repeats=3,
                         all_counts_match=all(r['sample_count_match'] for r in selected)))

def hss_quality(profile):
    rows = []
    for path in (ROOT / profile).glob('hss_*.json'):
        if path.name.endswith('_fixture.json'):
            continue
        rows.extend(json.loads(path.read_text()).get('rows', []))
    return dict(rows=len(rows), control_sequence_errors=sum(len(r.get('control_sequence_errors', [])) for r in rows),
                sample_count_mismatches=sum(r.get('sample_count_match') is False for r in rows),
                failed_rows=sum(r.get('passed') is False for r in rows))

quality = {p: hss_quality(p) for p in ['optimized_50_final', 'optimized_60']}
assert quality['optimized_50_final']['rows'] == 106
assert all(not q[k] for q in quality.values() for k in
           ['control_sequence_errors', 'sample_count_mismatches', 'failed_rows'])
retry = read('optimized_50_final', 'functional_transport_retries.json')
assert len(retry) == 3 and all(r['returncode'] == 0 and r['restore_match'] for r in retry)
runs60 = read('optimized_60', 'runs.json')
assert len(runs60) == 25 and all(r['returncode'] == 0 for r in runs60)

upper = {}
sram60 = read('optimized_60', 'sram.json')
assert len(sram60['rows']) == 14 and all(r['passed'] for r in sram60['rows'])
for transport in ['swd', 'jtag']:
    row = next(r for r in sram60['rows'] if r['transport'] == transport and r['requested_Hz'] == 60000000)
    rtt = read('optimized_60', f'rtt_{transport}_60000000.json')
    upper[transport] = dict(FCLK_Hz=row['FCLK_Hz'], actual_link_Hz=row['actual_link_Hz'],
                            SRAM_read_pipe_MB_s=row['read_pipe']['MB_s'],
                            SRAM_write_pipe_MB_s=row['write_pipe']['MB_s'],
                            RTT_host_MB_s=median_rows(rtt, 'host_MB_s'),
                            RTT_probe_MB_s=median_rows(rtt, 'probe_MB_s'),
                            HSS=read('optimized_60', 'hss_' + transport + '.json')['summary'][0])

report = dict(target='STM32F103ZE, HCLK48MHz; Zynq xc7z020',
              method='decimal MB/s; identical load and actual clocks; medians; complete data and restoration checks',
              common_50MHz_metrics=metrics, same_elf_pl_control=control,
              fixed_25MHz_zero_skip_confirmation=frontier, final_HSS_quality=quality,
              final_60MHz_jobs=len(runs60), upper_profile=upper,
              rejected_or_superseded=['optimized_50_rejected_unaligned', 'optimized_50'],
              functional_harness_correction='Explicit SWD HID service preference after prior JTAG; original failure retained, three forced-JTAG-history retries passed')
(ROOT / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')

lines = ['| 测试 | 最近基线 | 最终优化配对 | 变化 |', '|---|---:|---:|---:|']
for row in metrics:
    lines.append(f"| {row['name']} | {row['baseline']:.5f} | {row['optimized']:.5f} | {row['delta_percent']:+.2f}% |")
(ROOT / 'comparison-table.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(json.dumps({'metrics': len(metrics), 'HSS_quality': quality, 'upper_profile': upper}, indent=2))
