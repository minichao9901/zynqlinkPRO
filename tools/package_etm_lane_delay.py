"""Bind a fresh ELD1 bitstream to a freshly built PS ELF; no board/Flash access.

Refuses stale verified products, missing implemented lane proofs and FCLK<120MHz.
Board acceptance remains pending until actual loading, identity and captures pass.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(job_path,log_path,fpga):
    job=json.loads(job_path.read_text(encoding='utf-8-sig'))
    if (job['rawMode'],job['etmDdr'],job['laneDelay'],job['implementFclkHz'])!=(4,1,1,120000000):
        raise ValueError('Not the intended RAW4/DDR/ELD1 FCLK120 build')
    log=log_path.read_text(encoding='utf8')
    for proof in ('VERIFIED_BITSTREAM_READY','ORBTRACE_LANE_DELAY_VERIFIED count=5 VAR_LOAD=1 activeOutputs=5','ORBTRACE_LANE_ENDPOINTS_VERIFIED count=5','ORBTRACE_OVERSAMPLE_VERIFIED META=5 SYNC=5'):
        if not re.search('(?m)^'+re.escape(proof)+'$',log):raise ValueError('Missing completed implementation proof: '+proof)
    bit=fpga/'system_wrapper_verified.bit';clock=fpga/'verified_clock.json'
    start=datetime.fromisoformat(job['startedUtc']).timestamp()
    if any(p.stat().st_mtime<start for p in (bit,clock)):raise ValueError('Verified product predates this build; no old bit reuse')
    timing=json.loads(clock.read_text(encoding='utf8'))
    if timing['FCLK_max_Hz']<120000000 or min(timing['setup_slack_ns'],timing['hold_slack_ns'])<0:
        raise ValueError('ELD1 experiment must close the required FCLK120 timing')
    return job,timing


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',type=Path,required=True);p.add_argument('--log',type=Path,required=True)
    p.add_argument('--fpga-out',type=Path,required=True);p.add_argument('--ps-init',type=Path,required=True)
    p.add_argument('--verification-job',type=Path,help='Separate post-route verifier with linked parent-build and bit hashes')
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    job,timing=preflight(a.job,a.log,a.fpga_out)
    changed=subprocess.check_output(['git','diff','--name-only',job['source'],'--','fpga'],cwd=ROOT,text=True).splitlines()
    verification=None
    if a.verification_job:
        verification=json.loads(a.verification_job.read_text(encoding='utf-8-sig'))
        if (verification['parentJobSha256']!=sha(a.job) or verification['inputBitSha256']!=sha(a.fpga_out/'system_wrapper_verified.bit')
                or verification['verifierSha256']!=sha(ROOT/'fpga/verify_routed.tcl')):
            raise ValueError('Post-route verifier is not bound to this build, bit and verification script')
        if subprocess.run(['git','diff','--quiet',verification['source'],'--','fpga'],cwd=ROOT).returncode:
            raise ValueError('Current FPGA files differ from the actual verification commit')
    if changed and (not verification or set(changed)!={'fpga/verify_routed.tcl'}):
        raise ValueError('FPGA source differs from the frozen build; only a separately bound verifier update is allowed')
    stamp=json.loads((ROOT/'build/fpga_dma_global/swd_rtl_built.stamp').read_text(encoding='utf8'))
    actual={s.name:sha(s) for s in (ROOT/'fpga/rtl').glob('*.v')}
    if stamp!=actual:raise ValueError('Synthesis stamp does not match actual RTL')
    if not a.ps_init.is_file():raise FileNotFoundError(a.ps_init)
    a.out.mkdir(parents=True,exist_ok=False)
    ps=ROOT/'build'/(a.out.name+'-ps-'+datetime.now().strftime('%Y%m%dT%H%M%S%f'))
    if ps.exists():raise FileExistsError(ps)
    command=[sys.executable,str(ROOT/'tools/build_xusbps_daplink.py'),'--compact-code','--max-swclk-hz','60000000',
        '--timing',str(a.fpga_out.resolve()/'verified_clock.json'),'--out',str(ps.resolve())]
    run=subprocess.run(command,cwd=ROOT,capture_output=True)
    (a.out/'ps-build-output.txt').write_bytes(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError('Fresh PS build failed; existing known pair retained')
    build=json.loads((ps/'manifest.json').read_text(encoding='utf8'))
    sources={'probe.bit':a.fpga_out/'system_wrapper_verified.bit','application.elf':ps/'xusbps_daplink_dma.elf',
        'ps7_init.tcl':a.ps_init,'firmware-build.json':ps/'manifest.json','verified_clock.json':a.fpga_out/'verified_clock.json'}
    from test_etm_ddr_memory import reservation
    reservation(sources['application.elf'])
    for name,path in sources.items():shutil.copy2(path,a.out/name)
    manifest=dict(status='ELD1 STA passed; board loading/calibration pending; not Golden',accepted=False,
        rtlSourceRevision=job['source'],psSourceRevision=build['source_revision'],buildJob=job,verificationJob=verification,
        buildOptions=dict(rawMode=4,etmDdr=1,laneDelay=1,implementFclkHz=120000000,maxSwclkHz=60000000),
        timing=timing,rtlSha256=actual,capabilities=dict(perLaneInputDelay=True,autoCalibrationBoardVerified=False),
        files={name:dict(bytes=(a.out/name).stat().st_size,sha256=sha(a.out/name)) for name in sources},
        board=dict(loaded=False,verified=False))
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(out=str(a.out.resolve()),files=manifest['files'],boardAcceptance='pending'),indent=2))


if __name__=='__main__':main()
