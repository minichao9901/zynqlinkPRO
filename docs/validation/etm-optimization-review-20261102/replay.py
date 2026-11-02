import sys,json,shutil,time,traceback
from pathlib import Path
repo,source,dest=map(Path,sys.argv[1:4])
sys.path.insert(0,str(repo/'etm-service/tools'))
from trace_cli import engine_environment
from decode_stream import decode_stream
engine_environment()
dest.mkdir(parents=True,exist_ok=True)
for name in ['firmware.elf','sources.json','session.json']:
    if not (dest/name).exists():shutil.copy2(source/name,dest/name)
meta=json.loads((source/'decoded.json').read_text(encoding='utf8'))
raw=(source/'etm.bin' if (source/'etm.bin').exists() else source/'capture.bin').read_bytes()
t=time.perf_counter()
try:
    decoded=decode_stream(raw,dest/'firmware.elf',dest,meta['config'],json.loads((dest/'sources.json').read_text(encoding='utf8')),framing=meta.get('framing'),physical=meta.get('physical'),capture=meta.get('capture'))
    result=dict(ok=True,repo=str(repo),seconds=time.perf_counter()-t,summary=decoded['summary'],quality=decoded['quality'])
except Exception as ex:
    result=dict(ok=False,repo=str(repo),seconds=time.perf_counter()-t,error=str(ex),traceback=traceback.format_exc())
name='result-main.json' if repo.name=='zynqlinkPRO' else 'result-candidate.json'
(dest/name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False))
