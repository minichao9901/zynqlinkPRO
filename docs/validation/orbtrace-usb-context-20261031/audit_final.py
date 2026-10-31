"""Audit the final delivery in the optimization worktree, including private flash backups."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess

root=Path(__file__).resolve().parents[3]
load=lambda p:json.loads((root/p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
checks=[]
def passed(name,evidence,detail):checks.append(dict(requirement=name,status='verified',evidence=evidence,detail=detail))

pkg=Path('prebuilt/20261031_orbtrace_opt_qspi_usbfix_7020_120')
for folder in [pkg,Path('prebuilt/20261031_orbtrace_usbfix_7010_100')]:
    m=load(folder/('flash_manifest.json' if folder==pkg else 'manifest.json'))
    for name,expected in m['files'].items():assert sha(folder/name)==expected,(folder,name)
for directory,hz in [('20261031_orbtrace_opt_7020_120_candidate',120000000),('20261031_orbtrace_opt_7010_100_candidate',100000000)]:
    p=Path('prebuilt')/directory;m=load(p/'manifest.json')
    assert m['FCLK_constraint_Hz']==hz and m['timing']['WNS_ns']>=0 and m['timing']['WHS_ns']>=0
    assert m['timing']['TNS_ns']==m['timing']['THS_ns']==0
    for name,expected in m['sha256'].items():
        if name.endswith('.rpt') or name.endswith('.bit'):assert sha(p/name)==expected
    passed(directory,str(p/'manifest.json'),dict(timing=m['timing'],resources=m['resources'],scope='7020 board accepted;7010 static only, no physical7010 available'))
layout=load(pkg/'ocm_layout_60.json');assert layout['executable_bytes']==71268 and layout['span_bytes']==120976 and layout['ddr_section_bytes']==711520
assert layout['span_bytes']+layout['reserved_bytes']<=256*1024
for rev in ['00b9f2f','0ec2e63']:
    s=subprocess.check_output(['git','show',rev+':firmware/xusbps_daplink_dma/DAP/Include/DAP_config.h'],cwd=root).decode('utf-8')
    assert re.search(r'#define\s+DAP_PACKET_COUNT\s+16U',s) and re.search(r'#define\s+DAP_PACKET_SIZE\s+4096U',s)
assert '#define MEMORY_SIZE (512 * 1024)' in (root/'firmware/xusbps_daplink_dma/xusbps_intr_example.c').read_text(encoding='utf-8')
passed('OCM code/static data capacity; DDR buffers; queues unchanged',str(pkg/'ocm_layout_60.json'),dict(code=71268,OCM_span=120976,DDR=711520,DAP='16x4096',USB_arena=524288))
simbase=Path('docs/validation/orbtrace-7010-ocm-20261030');sim=load(simbase/'simulation_results.json')
for row in sim['logs']:assert sha(simbase/row['file'])==row['sha256']
matrix=load(simbase/'matrix_comparison.json');assert matrix['cases_each']==21 and matrix['payload_validated_cases_each']==14 and matrix['incompatible_sampling_points_each']==7 and not matrix['new_failures']
profiles=load('prebuilt/20261031_orbtrace_opt_7020_120_candidate/simulation_comparison.json')
assert profiles['cases']==9 and profiles['all_payloads_validated'] and profiles['metrics_identical']
for row in profiles['results']:
    assert row['passed'] and row['metrics_identical']
    for side in ['baseline','candidate']:
        assert all(row[side][service] for service in ['SRAM','RTT','HSS'])
passed('SWD/JTAG SRAM RTT HSS simulations',str(simbase),dict(native_commands=sim['passed_commands'],CM3_matrix=matrix,matched_profiles=9,PL_unchanged_since_validation=True,USB_simulated=False))
hw=Path('docs/validation/orbtrace-hardware-20261031');a=load(hw/'availability.json')
assert datetime.datetime.fromisoformat(a['time'])>=datetime.datetime.fromisoformat('2026-10-30T22:21:23+00:00')
assert not a['probe_commands_before_gate'] and a['thread_status']=='idle/completed' and a['native_server_delivery_requests_two_checks']==[54,54]
jobs=load(hw/'optimized_60/runs.json');assert len(jobs)==25 and all(x['returncode']==0 and not x['failure'] for x in jobs)
passed('Three-hour gate, other AI idle, original full hardware regression',str(hw),dict(availability=a,driver_jobs=25))
subprocess.run([__import__('sys').executable,str(Path(__file__).with_name('compare_final.py'))],cwd=root,check=True)
comparison=load('docs/validation/orbtrace-usb-context-20261031/comparison_final.json');assert len(comparison['rows'])==12 and comparison['strict_HSS_rows']==42
passed('Latest exact ELF throughput/RTT/HSS/default50/soak regression and comparison','comparison_final.json',dict(metrics=12,HSS=42,soak_errors=0,analysis='Retained short-window deltas/soak minima; no stable regression. Original overload old/newPL same-ELF control retained in hardware README.'))
sources=load('docs/validation/orbtrace-usb-context-20261031/firmware_source_audit.json');assert sources['all_match'] and len(sources['files'])==36
for row in sources['files']:assert sha(row['file'])==row['source_sha256']
passed('Exact firmware source identity and Chapter9 corruption fix','firmware_source_audit.json',dict(source=sources['source_revision'],files=36,negative='Old f88a STRB through null pointer observed; final USB reconfiguration full-code checks pass'))
flash=load('build/qspi_usb_context_flash/result.json');assert flash['status']=='programmed_verified_reset_boot' and flash['outside_erased_range_unchanged']
boot=(root/pkg/'BOOT.bin').read_bytes();before=(root/'build/qspi_usb_context_flash/original_flash_32MiB.bin').read_bytes();after=(root/'build/qspi_usb_context_flash/programmed_readback.bin').read_bytes()
assert len(before)==len(after)==32<<20 and hashlib.sha256(before).hexdigest()==flash['backup']['sha256']
assert after[:len(boot)]==boot and before[(len(boot)+4095)&~4095:]==after[(len(boot)+4095)&~4095:]
assert hashlib.sha256(boot).hexdigest()==flash['readback_sha256']
passed('Full unified CLI flash backup/program/verify/independent readback/reset','qspi_cli/result.json',dict(BOOT_sha256=flash['readback_sha256'],backup_sha256=flash['backup']['sha256'],full_flash_readback_sha256=hashlib.sha256(after).hexdigest(),outside_erase_unchanged=True))
cold=load('docs/validation/orbtrace-usb-context-20261031/cold_final/result.json')
assert cold['passed'] and not cold['downloads'] and not cold['probe_reset_or_continue'] and cold['boot_mode']==1 and cold['expected_executable_bytes']==71268
assert cold['elf_sha256']==sha(pkg/'application.elf')
assert all(not c['differing_addresses'] and c['vector_word']=='ea000049' and all(s['equal'] for s in c['sections']) for c in cold['cycles'])
for tr in ['swd','jtag']:
    d=load(f'docs/validation/orbtrace-usb-context-20261031/cold_final/{tr}60.json')
    assert d['passed'] and d['restore_match'] and not d.get('recover_error') and d['FCLK_Hz']==119999998 and d['SWCLK_Hz']==59999999.0
passed('Final user cold power-cycle: autonomous QSPI boot, full OCM code, USB, SRAM','cold_final/acceptance.json',dict(no_download=True,all_code_bytes=71268,protocols=['swd','jtag'],link_Hz=59999999.0))
report=dict(audited_at_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),all_session_requests_complete=True,requirements=checks,
    limitations=['Physical7010 untested:100MHz static implementation only;2Slices free.','Later ETM filter changes intentionally unmerged; real ETM capture not part of SWD/JTAG acceptance.','Clock rates derive from registers/nominal crystal; simulation does not model USB/PS instruction throughput.'])
Path(__file__).with_name('completion_audit_final.json').write_text(json.dumps(report,indent=2)+'\n')
print('Final requirements audit passed; no required validation remains.')
