from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

root=Path(__file__).resolve().parents[2]
base=Path(__file__).resolve().parent
dest=root/'docs/validation/performance-limits-20261101'
raw=dest/'raw'
raw.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
for name in ['summary.json','interleave-summary.json']:
    shutil.copyfile(base/name,dest/name)
selected=[];excluded=[]
for p in sorted(base.rglob('*')):
    if not p.is_file():continue
    relative=p.relative_to(base).as_posix()
    item=dict(localPath=str(p),bytes=p.stat().st_size,sha256=sha(p))
    if p.suffix.lower() in ['.json','.txt','.tcl','.py','.log']:
        target=raw/relative
        if p.suffix.lower()=='.log':target=Path(str(target)+'.txt')
        target.parent.mkdir(parents=True,exist_ok=True)
        assert not target.exists()
        shutil.copyfile(p,target)
        item['archivePath']=target.relative_to(dest).as_posix()
        assert sha(target)==item['sha256']
        selected.append(item)
    else:
        item['reason']='Local payload/SRAM backup/OCM snapshot or reproducible STM32 RAM producer, not a new Zynq delivery'
        excluded.append(item)
drivers=dest/'drivers';drivers.mkdir(exist_ok=False)
sources=['validate_fclk_performance.py','validate_fclk_edge_cases.py','run_fclk_comparison.py',
         'validate_stream_debug_interleave.py','benchmark_rtt_forward.py','benchmark_probe_stream.py',
         'h743_peak.py','dap_pipeline_bench.py','test_probe_board.py','test_swd_lowfreq_board.py',
         'probe_build_info.py','run_f103_jtag_fixture.py','test_orbtrace_board.py','verify_probe_ocm_code.py']
source_rows=[]
for name in sources:
    p=root/'tools'/name
    q=drivers/(name+'.txt');shutil.copyfile(p,q)
    source_rows.append(dict(source='tools/'+name,sha256=sha(p),snapshot=q.relative_to(dest).as_posix()))
pairs=[]
for name in ['golden','fclk133-release-20261101','fclk133-swd-fixed-test-20261101']:
    folder=root/'prebuilt'/name
    row=dict(path=folder.relative_to(root).as_posix(),newBuild=False,files={})
    for name2 in ['probe.bit','application.elf','ps7_init.tcl']:
        p=folder/name2
        subprocess.run(['git','ls-files','--error-unmatch',str(p.relative_to(root))],cwd=root,
                       stdout=subprocess.DEVNULL,check=True)
        row['files'][name2]=dict(bytes=p.stat().st_size,sha256=sha(p))
    pairs.append(row)
manifest=dict(createdAtUtc=datetime.now(timezone.utc).isoformat(),
    sourceHeadBeforeEvidenceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
    predecessor='ec6d028847d55e9dd4eea7aab11c9a59b98564b5',hardwareWrites='RAM-only probe loads, bounded target SRAM/trace/debug fixtures',
    RTLModified=False,ZynqFirmwareModified=False,targetFlashWrites=False,QSPIWrites=False,
    sourceSnapshots=source_rows,artifactPairs=pairs,archivedFiles=selected,localOnlyFiles=excluded,
    sourceSnapshotNote='End-of-task source snapshots. Phase/job records contain invocation-time hashes where recorded; first complete interleave driver is also in raw/drivers. Early fixed-profile tests preceded host-driver commits; core benchmark tools were unchanged. No firmware was rebuilt.',
    acceptanceScope='Measured F103 function/performance only; J-Scope sample-phase behavior and full SWJ reconnect limitations remain, fixed pair not promoted')
write(dest/'evidence.json',manifest)
print('Archived',len(selected),'evidence files;',sum(x['bytes'] for x in selected),'bytes;',len(excluded),'local binaries inventoried')
