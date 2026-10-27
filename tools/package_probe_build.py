"""Package a source-matched, timing-verified pair after end-to-end measurements."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--measurements',nargs='+',type=Path,required=True)
    a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    build=root/'build/fpga_dma_global';fw=root/'build/xusbps_daplink_dma/O3'
    bit=build/'system_wrapper_verified.bit';elf=fw/'xusbps_daplink_dma.elf'
    stamp=build/'swd_rtl_built.stamp'
    current=json.loads(subprocess.check_output(['python',str(root/'tools/fpga_rtl_stamp.py')],text=True))
    assert current==json.loads(stamp.read_text()),'RTL differs from synthesized source'
    assert bit.stat().st_mtime>=stamp.stat().st_mtime,'bitstream predates current synthesis'
    fm=json.loads((fw/'manifest.json').read_text())
    assert sha(elf)==fm['elf_sha256']
    src=root/'firmware/xusbps_daplink_dma'
    assert fm['source_sha256']=={str(p.relative_to(src)):sha(p) for p in src.rglob('*') if p.is_file()},'firmware source changed'
    reports=[json.loads(p.read_text()) for p in a.measurements]
    for p,r in zip(a.measurements,reports):
        assert r['rows'] and r['restore_match'],str(p)
        for label,path in [('bit',bit),('elf',elf)]:assert r['artifacts'][label]['sha256']==sha(path),(p,label)
        for row in r['rows']:
            assert row.get('swd_errors',row.get('errors',0))==0,(p,row)
            assert row.get('sample_count_match',row.get('all_published_received',False)),(p,row)
    assert any('host_MB_s' in row for r in reports for row in r['rows']),'missing RTT acceptance'
    assert any('effective_Hz' in row for r in reports for row in r['rows']),'missing HSS acceptance'
    out=root/'prebuilt'
    shutil.copy2(bit,out/'zynqlink_probe.bit');shutil.copy2(elf,out/'zynqlink_probe.elf')
    manifest=dict(feature='RTT/HSS PL packet BRAM -> CDMA -> HP0 -> DDR -> USB',
        built_at=datetime.now().astimezone().isoformat(),
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        base_commit='35f7cf631d1510259bfd0da2f616dca28488e995',branch='codex/probe-rtt-hss',
        artifacts={p.name:sha(p) for p in [out/'zynqlink_probe.bit',out/'zynqlink_probe.elf']},
        fpga_timing=json.loads((build/'verified_clock.json').read_text()),
        firmware_options=fm['options'],rtl_source_sha256=current,
        firmware_source_sha256=fm['source_sha256'],bsp_sha256=fm['bsp_sha256'],
        measurements={str(p.relative_to(root) if p.is_absolute() else p):sha(p) for p in a.measurements})
    (out/'probe_build_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    names=['ps7_init.tcl','zynqlink_packet.bit','zynqlink_packet.elf','zynqlink_probe.bit','zynqlink_probe.elf']
    (out/'SHA256SUMS').write_text(''.join(sha(out/n)+'  '+n+'\n' for n in names))
    print(json.dumps(manifest['artifacts'],indent=2))


if __name__=='__main__':main()
