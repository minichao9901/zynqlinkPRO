"""Package the authorized 133.333 MHz release from a newly verified routed DCP.

Only FCLK0 source/dividers differ in the generated PS initialization. No hardware
or Flash is touched. Board acceptance is explicitly pending in this manifest.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,re,shutil,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fpga-out',type=Path,required=True)
    p.add_argument('--ps-init',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ps-out',type=Path,required=True)
    a=p.parse_args()
    job=json.loads((a.fpga_out/'job.json').read_text())
    clock=json.loads((a.fpga_out/'verified_clock.json').read_text())
    if job.get('returncode')!=0 or clock['FCLK_max_Hz']!=133333333 or clock['RTL_DEBUG']!=0:
        raise ValueError('Not a completed release133 verification')
    if min(clock['setup_slack_ns'],clock['hold_slack_ns'])<0:raise ValueError('Failed timing')
    summary=(a.fpga_out/'timing_verified.rpt').read_text()
    if 'All user specified timing constraints are met.' not in summary:raise ValueError('Incomplete timing')
    for name in ('system_wrapper_verified.bit','verified_clock.json'):
        if sha(a.fpga_out/name)!=job[name]['sha256']:raise ValueError('Verification identity changed')
    actual={p.name:sha(p) for p in (ROOT/'fpga/rtl').glob('*.v')}
    if actual!=job['rtlSha256']:raise ValueError('RTL differs from verified checkpoint')
    if a.out.exists() or a.ps_out.exists():raise FileExistsError('Output directories must be new')
    source=a.ps_init.read_bytes().decode('utf8')
    # PS7 init has one clock table per silicon revision. Keep every unrelated
    # line byte-for-byte, including IO/ARM/DDR PLL feedback and FCLK1 /9.
    pattern=r'(?m)^(\s*mask_write 0XF8000170 0x03F03F30 )0x[0-9A-Fa-f]{8}'
    patched,count=re.subn(pattern,r'\g<1>0x00100A20',source)
    if count!=3:raise ValueError('Unexpected PS7 init clock tables')
    if not re.search(r'mask_write 0XF8000180 0x03F03F30 0x00300300',source):
        raise ValueError('Expected unchanged 200MHz FCLK1 configuration')
    a.out.mkdir(parents=True)
    run=subprocess.run([sys.executable,str(ROOT/'tools/build_xusbps_daplink.py'),
        '--compact-code','--max-swclk-hz','60000000','--timing',str((a.fpga_out/'verified_clock.json').resolve()),
        '--out',str(a.ps_out.resolve())],cwd=ROOT,capture_output=True)
    (a.out/'ps-build-output.txt').write_bytes(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError('Fresh paired firmware build failed')
    from test_etm_ddr_memory import reservation
    elf=a.ps_out/'xusbps_daplink_dma.elf';reservation(elf)
    sources={'probe.bit':a.fpga_out/'system_wrapper_verified.bit','application.elf':elf,
             'verified_clock.json':a.fpga_out/'verified_clock.json','firmware-build.json':a.ps_out/'manifest.json',
             'fpga-verification-job.json':a.fpga_out/'job.json'}
    for name,path in sources.items():shutil.copyfile(path,a.out/name)
    (a.out/'ps7_init.tcl').write_bytes(patched.encode('utf8'))
    note=dict(basePath=str(a.ps_init),baseSha256=sha(a.ps_init),changedRegister='0xf8000170',
              changedTables=count,mask='0x03f03f30',value='0x00100a20',source='ARM PLL',
              divisor0=10,divisor1=1,unchangedOtherLines=True,
              physicalFrequencyCounterUsed=False,nominalFclkHz=133333333.33333333,
              firmwareCalculatedFclkHz=133333332)
    (a.out/'ps-init-clock-change.json').write_text(json.dumps(note,indent=2)+'\n')
    files={name:dict(bytes=(a.out/name).stat().st_size,sha256=sha(a.out/name))
           for name in [*sources,'ps7_init.tcl','ps-init-clock-change.json']}
    manifest=dict(status='release133 STA/bitgen passed; hardware acceptance pending; not Golden',accepted=False,
        createdUtc=datetime.now(timezone.utc).isoformat(),rtlSourceRevision=job['routedRtlSource'],
        psSourceRevision=json.loads((a.ps_out/'manifest.json').read_text())['source_revision'],
        verificationSource=job['source'],buildOptions=dict(rawMode=4,etmDdr=1,laneDelay=1,RTL_DEBUG=0,
            implementFclkHz=133333333,maxSwclkHz=60000000,FCLK0_source='ARM PLL',FCLK0_divisor=10),
        ddrReservation=dict(base='0x39c00000',endExclusive='0x40000000',bytes=104857600),
        clockPolicy='Boot/offline capture ARM PLL /10; normal DAP_SWJ_Clock retains Golden IO PLL policy and is rejected while DDR owned',
        timing=clock,rtlSha256=actual,files=files)
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(output=str(a.out),files=files),indent=2))


if __name__=='__main__':main()
