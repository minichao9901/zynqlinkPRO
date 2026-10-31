"""Completion audit for the optimization worktree and its private local backups.

Requires the complete optimization branch, including the earlier regression
artifacts. This is an archived delivery audit, not the portable CLI verifier.
"""
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess

root = Path(__file__).resolve().parents[3]
load = lambda p: json.loads((root/p).read_text(encoding='utf-8'))
sha = lambda b: hashlib.sha256(b).hexdigest()
checks = []


def checked(name, evidence, detail):
    checks.append(dict(requirement=name, status='verified', evidence=evidence, detail=detail))


for directory, frequency in [('20261031_orbtrace_opt_7020_120_candidate',120000000),
                             ('20261031_orbtrace_opt_7010_100_candidate',100000000)]:
    base = Path('prebuilt')/directory
    m = load(base/'manifest.json')
    assert m['FCLK_constraint_Hz']==frequency
    assert m['timing']['WNS_ns']>=0 and m['timing']['WHS_ns']>=0
    assert m['timing']['TNS_ns']==m['timing']['THS_ns']==0
    for name, expected in m['sha256'].items():
        path = base/name
        assert sha((root/path).read_bytes())==expected, path
        assert sha(subprocess.check_output(['git','show','HEAD:'+path.as_posix()],cwd=root))==expected, path
    checked(directory, str(base/'manifest.json'), dict(timing=m['timing'],resources=m['resources'],
        scope='7020 physical SWD/JTAG acceptance; 7010 static implementation only'))

layout = load('prebuilt/20261031_orbtrace_opt_7020_120_candidate/ocm_layout_60.json')
assert layout['span_bytes']+layout['reserved_bytes']<=256*1024
assert layout['executable_bytes']==71300 and layout['ddr_section_bytes']==711520
config = (root/'firmware/xusbps_daplink_dma/DAP/Include/DAP_config.h').read_text(encoding='utf-8')
assert re.search(r'#define\s+DAP_PACKET_COUNT\s+16U',config)
assert re.search(r'#define\s+DAP_PACKET_SIZE\s+4096U',config)
assert '#define MEMORY_SIZE (512 * 1024)' in (root/'firmware/xusbps_daplink_dma/xusbps_intr_example.c').read_text(encoding='utf-8')
checked('OCM capacity and unchanged USB/DAP queues','prebuilt/20261031_orbtrace_opt_7020_120_candidate/ocm_layout_60.json',
        dict(OCM_span=layout['span_bytes'],code=layout['executable_bytes'],DAP='16x4096',USB_arena=512*1024))

simbase = Path('docs/validation/orbtrace-7010-ocm-20261030')
sim = load(simbase/'simulation_results.json')
for item in sim['logs']:
    assert sha((root/simbase/item['file']).read_bytes())==item['sha256']
matrix = load(simbase/'matrix_comparison.json')
assert matrix['cases_each']==21 and matrix['payload_validated_cases_each']==14
assert matrix['incompatible_sampling_points_each']==7 and not matrix['new_failures']
profiles = load('prebuilt/20261031_orbtrace_opt_7020_120_candidate/simulation_comparison.json')
assert profiles['cases']==9 and profiles['all_payloads_validated'] and profiles['metrics_identical']
assert {p['transport'] for p in profiles['results']}=={'swd','jtag'}
for p in profiles['results']:
    assert p['passed'] and p['metrics_identical']
    for side in ['baseline','candidate']:
        for service in ['SRAM','RTT','HSS']:
            assert p[side][service]
checked('SWD/JTAG SRAM, RTT, HSS simulation',str(simbase/'simulation_results.json'),
        dict(native_commands=sim['passed_commands'],CM3_matrix=matrix,matched_performance_profiles=9,USB_modeled=False))

hw = Path('docs/validation/orbtrace-hardware-20261031')
availability = load(hw/'availability.json')
gate = datetime.datetime.fromisoformat('2026-10-30T22:21:23+00:00')
assert datetime.datetime.fromisoformat(availability['time'])>=gate
assert availability['probe_commands_before_gate'] is False
assert availability['thread_status']=='idle/completed'
assert availability['native_server_delivery_requests_two_checks']==[54,54]
checked('Three-hour gate and other AI idle before probe use',str(hw/'availability.json'),availability)
jobs = load(hw/'optimized_60/runs.json')
assert len(jobs)==25 and all(j['returncode']==0 and not j['failure'] for j in jobs)
for j in jobs:
    assert j['restore_match'] is not False and j['fixture_restore'] is not False
comparison = load(hw/'comparison.json')
assert len(comparison['common_50MHz_metrics'])==11
for row in comparison['common_50MHz_metrics']:
    assert abs(row['delta_percent']-(row['optimized']/row['baseline']-1)*100)<1e-9
checked('Physical probe regression, recent-baseline comparison, degradation analysis',str(hw/'comparison.json'),
        dict(driver_jobs=25,matched_metrics=11,max_absolute_delta_percent=max(abs(r['delta_percent']) for r in comparison['common_50MHz_metrics']),
             analysis='README: same-ELF old/new PL controls, USB packetization/backpressure, retained failures and fixed SWJ/STOP defects'))

sota = load('docs/validation/orbtrace-sota-20261031/comparison.json')
assert len(sota['comparison'])==12 and sota['strict_hss_rows']==42
checked('Reproduce original 50/60MHz SOTA','docs/validation/orbtrace-sota-20261031/comparison.json',
        dict(metrics=12,strict_hss_rows=42,scope='96MHz RAM fixtures; historical pair rerun for throughput/RTT; instantaneous soak minima differ as documented'))

pkg = Path('prebuilt/20261031_orbtrace_opt_qspi_7020_120')
manifest = load(pkg/'flash_manifest.json')
for name, expected in manifest['files'].items():
    assert sha((root/pkg/name).read_bytes())==expected,name
    assert sha(subprocess.check_output(['git','show','HEAD:'+(pkg/name).as_posix()],cwd=root))==expected,name
boot = (root/pkg/'BOOT.bin').read_bytes()
old = (root/'build/qspi_boot/backup/original_flash_32MiB.bin').read_bytes()
new = (root/'build/qspi_boot/post_program/programmed_flash_32MiB.bin').read_bytes()
readback = load('docs/validation/orbtrace-qspi-20261031/readback_result.json')
assert len(old)==len(new)==32<<20 and sha(old)==readback['original_backup_sha256']
assert sha(new)==readback['full_readback_sha256'] and new[:len(boot)]==boot
assert new[(len(boot)+4095)&~4095:]==old[(len(boot)+4095)&~4095:]
cli = load('docs/validation/orbtrace-qspi-20261031/cli_verify_pass/result.json')
assert cli['boot_trace']==[0x53544730,0x20261031,0x10008,1,2,0x600,0,1]
checked('QSPI persistence, backup, readback, OCM handoff and unified CLI',str(pkg/'flash_manifest.json'),
        dict(boot_sha256=sha(boot),software_no_halt_reset=True,CLI_commit='d564dec',
             physical_SWD60='post_boot_swd.json: payload/RCC/SRAM restored',
             main_entry='E:/zynqlinkPRO/toolbox.py probe-flash',source='74c4802'))
srst = load('docs/validation/orbtrace-qspi-20261031/hardware_srst_check/result.json')
assert not srst['hardware_reset_observed'] and srst['diagnostic_marker_restored']
checks.append(dict(requirement='Physical button/power-cycle after programming',status='pending_user',
    evidence='hardware_srst_check/result.json',detail='Cable SRST did not trigger reset; user action after programming not yet confirmed. No further download/programming needed.'))
report = dict(audited_at_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    authoritative_worktree=str(root),
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
    original_delayed_regression_objective_verified=True,all_session_requests_complete=False,requirements=checks)
(Path(__file__).with_name('completion_audit.json')).write_text(json.dumps(report,indent=2)+'\n')
print('Original optimization/simulation/delayed regression and QSPI software checks verified; physical reset remains pending user.')
