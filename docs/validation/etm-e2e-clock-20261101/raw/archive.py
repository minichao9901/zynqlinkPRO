from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess

base=Path(__file__).resolve().parent
root=base.parents[1]
dest=root/'docs/validation/etm-e2e-clock-20261101'
raw=dest/'raw';raw.mkdir(exist_ok=False)
tokens=[p.read_bytes().strip() for p in base.rglob('cli-token')]
files=[]
def sha(blob):return hashlib.sha256(blob).hexdigest()
def write_json(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def archive(p,relative,transform=None):
    original=p.read_bytes();blob=original
    if transform:blob=(json.dumps(transform(json.loads(original.decode('utf-8-sig'))),ensure_ascii=False,indent=2)+'\n').encode('utf8')
    for token in tokens:
        if token:blob=blob.replace(token,b'<redacted-local-token>')
    q=raw/relative;q.parent.mkdir(parents=True,exist_ok=True)
    assert not q.exists();q.write_bytes(blob)
    files.append(dict(localPath=str(p),archivePath=q.relative_to(dest).as_posix(),
        originalSha256=sha(original),sha256=sha(blob),bytes=len(blob),
        transformed=bool(transform) or original!=blob))

def selected_steps(steps):
    previous={};out=[]
    for index,step in enumerate(steps):
        req=step.get('request',{})
        if req.get('op')=='read':
            key=(req.get('page'),req.get('selector'))
            value=json.dumps(step.get('result',{}).get('value'),sort_keys=True,ensure_ascii=False)
            if previous.get(key)==value:continue
            previous[key]=value
        out.append(dict(originalIndex=index,**step))
    return dict(projection='All mutations and state-changing observations; identical read polling omitted',
                originalSteps=len(steps),selectedSteps=out)

for name in ['load','ab','ab-full-clock','ab-measured','ab-repeat','package-default-clock','final-state']:
    for p in sorted((base/name).rglob('*')):
        if not p.is_file() or p.suffix not in ['.json','.txt','.tcl','.log']:continue
        if p.name.startswith('echo-'):continue # Complete echo rows also present in captures.json.
        relative=p.relative_to(base).as_posix()
        if p.name=='steps.json':
            archive(p,relative.replace('steps.json','steps-selected.json'),selected_steps)
        elif p.name=='summary.json':
            archive(p,relative,lambda d:{k:v for k,v in d.items() if k!='captures'})
        else:archive(p,relative+('.txt' if p.suffix=='.log' else ''))
for name in ['comparison.json','analysis.json','delivery.json','final-board.json','final-processes.json',
             'web-tests.txt','python-tests.txt','ab-console.txt','ab-full-clock-console.txt',
             'ab-measured-console.txt','ab-repeat-console.txt','package-default-clock-console.txt',
             'analyze.py','analyze_all.py','finish_board.py','archive.py']:
    if (base/name).exists():archive(base/name,name)
shutil.copyfile(base/'comparison.json',dest/'comparison.json')
archive(root/'build/bridge-package/latest-verification.json','package-offline-verification.json')
archive(root/'dist/zynq-etm-bridge/package-manifest.json','package-manifest.json')
archive(root/'dist/zynq-etm-bridge/package-check.json','package-check.json')
sources=[]
for name in ['etm-service/server.py','etm-service/trace.py','etm-service/tools/zynq_la.py',
             'etm-service/tools/dap_pipeline_bench.py','etm-service/tools/trace_cli.py',
             'etm-service/tools/trace_cli_hardware.py','etm-service/tools/native_web_capture.py',
             'etm-service/web/app/target.js','etm-service/web/app/view.js',
             'web/app/automation/trace.js','tools/stress_etm_web.py','tools/build_bridge.py']:
    q=dest/'drivers'/(name.replace('/','__')+'.txt');q.parent.mkdir(exist_ok=True)
    shutil.copyfile(root/name,q)
    sources.append(dict(source=name,snapshot=q.relative_to(dest).as_posix(),sha256=sha(q.read_bytes())))
runtime=json.loads((base/'runtime-measured/toolbox-runtime.json').read_text(encoding='utf8'))
record_ids=set()
for name in ['ab','ab-measured','ab-repeat','package-default-clock']:
    p=base/name/'captures.json'
    if p.exists():record_ids.update(r['record'] for r in json.loads(p.read_text(encoding='utf8')))
record_rows=[]
for sid in sorted(record_ids):
    # Frozen EXE uses a new, explicitly isolated data directory.
    folder=Path(runtime['recordsDirectory'])/sid
    if not folder.exists():folder=base/'package-validation/records'/sid
    payloads={}
    for name in ['capture.bin','capture.frm1']:
        p=folder/name
        if p.exists():payloads[name]=dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
    for name in ['session.json','decoded.json','decode-performance.json','ddr-capture.json','ddr-demux.json','store/manifest.json']:
        p=folder/name
        if p.exists():archive(p,'records/'+sid+'/'+name)
    record_rows.append(dict(id=sid,localDirectory=str(folder),localOnlyPayloads=payloads))
pair=root/'prebuilt/fclk133-release-20261101'
manifest=dict(createdAtUtc=datetime.now(timezone.utc).isoformat(),
    sourceRevision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
    RTLModified=False,ZynqFirmwareModified=False,targetFlashWrites=False,QSPIWrites=False,
    pair=str(pair),pairFiles={n:sha((pair/n).read_bytes()) for n in ['probe.bit','application.elf','ps7_init.tcl']},
    files=files,sourceSnapshots=sources,records=record_rows,
    note='Native stores and payloads remain local; hashes above. Identical UI read polling omitted with full original file hash retained. Echo data retained once per captures.json. No credentials archived.')
write_json(dest/'evidence.json',manifest)
print('Archived',len(files),'reports and',len(sources),'sources;',sum(v['bytes'] for v in files),'bytes;',len(record_rows),'record identities')
