"""Offline full-Web decode benchmark on a read-only real capture, no board I/O."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import threading
import time
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etm-service/tools'))


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--repeat',type=int,default=3)
    p.add_argument('--port',type=int,default=8883)
    a=p.parse_args()
    if not 1<=a.repeat<=10:p.error('repeat must be 1..10')
    output=a.out.resolve();output.mkdir(parents=True,exist_ok=False)
    original=a.record.resolve();metadata=json.loads((original/'session.json').read_text(encoding='utf8'))
    raw=original/metadata['input']
    if raw.name!='capture.bin':p.error('this offline audit requires captured ETM BIN')
    fingerprints={f:hashlib.sha256((original/f).read_bytes()).hexdigest() for f in ['capture.bin','firmware.elf','sources.json']}
    # Prove product startup defeats inherited legacy developer flags.
    os.environ.update(ETM_STORE_WRITE='0',ETM_STORE_ENGINE='python',ETM_NATIVE_FORMAT='text')
    temporary=output/'tmp';temporary.mkdir();os.environ['TEMP']=os.environ['TMP']=str(temporary)
    runtime=output/'runtime';runtime.mkdir();token=secrets.token_hex(32);(runtime/'cli-token').write_text(token)
    spec=importlib.util.spec_from_file_location('offline_workbench',ROOT/'web/tools/dev/serve-etm.py')
    service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
    application=service.create_application(ROOT/'etm-service',ROOT/'web',runtime/'cli-token')
    backend=sys.modules['etm_toolbox_backend'];backend.RECORDS=output/'records';backend.RECORDS.mkdir()
    from flask import request,jsonify,abort
    @backend.app.before_request
    def offline_guard():
        if request.path=='/api/status':
            return jsonify(connected=False,offline=True,rates=[],error='',captureProtocol=2,
                           zynq={'ready':False,'message':'离线性能验收：硬件探测已禁用'})
        if request.path in ('/api/capture','/api/native-capture'):abort(403)
    from waitress.server import create_server
    server=create_server(application,host='127.0.0.1',port=a.port,threads=16,connection_limit=64)
    url=f'http://127.0.0.1:{a.port}'
    save(runtime/'toolbox-runtime.json',{'protocol':'workbench/1','url':url,'pid':os.getpid(),
         'status':'serving','offline':True,'decodeEngineProfile':backend.current_profile()})
    report={'offline':True,'sourceRecord':str(original),'inputSha256':fingerprints,
            'engineProfile':backend.current_profile(),'rows':[]}
    def api(path,value=None):
        data=json.dumps(value).encode() if value is not None else None
        with urlopen(Request(url+'/etm/api/'+path,data=data,headers={'Content-Type':'application/json'}),timeout=30) as r:return json.load(r)
    def campaign():
        try:
            for trial in range(1,a.repeat+1):
                sid=f'record-native-1s-r{trial}-{secrets.token_hex(4)}';folder=backend.RECORDS/sid;folder.mkdir()
                for f in ['capture.bin','firmware.elf','sources.json']:shutil.copy2(original/f,folder/f)
                meta=dict(metadata,name=f'离线1s原生验收 · 第{trial}次',created=time.time(),decodeStatus='pending')
                meta.pop('summary',None);meta.pop('error',None);save(folder/'session.json',meta)
                started=time.perf_counter();job=api('decode/'+sid,{})
                deadline=time.monotonic()+300
                while True:
                    state=api('jobs/'+job['job'])
                    if state['state'] not in backend.ACTIVE:break
                    if time.monotonic()>deadline:raise TimeoutError('offline decode exceeded 300 seconds')
                    time.sleep(.025)
                wall=time.perf_counter()-started
                if state['state']!='done':raise RuntimeError(state)
                decoded=json.loads((folder/'decoded.json').read_text(encoding='utf8'))
                banned=[str(f.relative_to(folder)) for f in folder.rglob('*') if f.is_file() and f.name in
                        ('native.jsonl','events.jsonl','packets.jsonl','elements.jsonl','browse-columns.tsv','browse-v3.sqlite')]
                assert not banned,banned
                manifest=json.loads((folder/'store/manifest.json').read_text(encoding='utf8'))
                assert manifest['engine']['name']=='native' and not manifest['engine']['fallback'],manifest['engine']
                assert manifest['bindings']['processing']['engine']=='native'
                old=json.loads((original/'decoded.json').read_text(encoding='utf8'))
                assert decoded['summary']==old['summary'],'summary differs from retained text result'
                for k,v in old['quality'].items():
                    if k in decoded['quality']:assert decoded['quality'][k]==v,(k,v,decoded['quality'][k])
                row={'trial':trial,'record':sid,'completeProcessingWallSeconds':wall,'state':state['state'],
                     'summaryMatchesLegacy':True,'sharedQualityMatchesLegacy':True,'summary':decoded['summary'],
                     'quality':decoded['quality'],'performance':json.loads((folder/'decode-performance.json').read_text(encoding='utf8')),
                     'files':{str(f.relative_to(folder)):f.stat().st_size for f in folder.rglob('*') if f.is_file()},
                     'largeJsonIntermediates':banned}
                report['rows'].append(row);save(output/'results.json',report)
                print(f'trial {trial}: {wall:.3f}s, C++ engine, no event JSONL, counts/quality unchanged, record={sid}',flush=True)
            report['inputUnchanged']=all(hashlib.sha256((original/f).read_bytes()).hexdigest()==h for f,h in fingerprints.items())
            assert report['inputUnchanged'];save(output/'results.json',report);save(output/'ready.json',{'ready':True,'runtime':str(runtime),'records':[x['record'] for x in report['rows']]})
            print('OFFLINE_BENCH_READY '+str(output/'ready.json'),flush=True)
        except BaseException as error:
            save(output/'failure.json',{'error':str(error)});print('OFFLINE_BENCH_FAILED '+str(error),flush=True)
    threading.Thread(target=campaign,daemon=True).start()
    print('BROWSER_URL '+url+'/?trace-cli='+token+'#etm',flush=True)
    try:server.run()
    finally:server.close();server.task_dispatcher.shutdown()


if __name__=='__main__':main()
