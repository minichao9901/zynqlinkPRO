"""AI offline acceptance of the real portable EXE; all hardware routes disabled."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import uuid
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf8',errors='replace')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--port',type=int,default=8890);p.add_argument('--keep-running',action='store_true')
    a=p.parse_args(argv);package=a.package.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    if a.port==0:
        with socket.socket() as available:
            available.bind(('127.0.0.1',0));a.port=available.getsockname()[1]
    manifest=json.loads((package/'package-manifest.json').read_text(encoding='utf8'))
    for item in manifest['files']:
        path=(package/item['path']).resolve()
        if not path.is_relative_to(package) or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Package hash mismatch: '+item['path'])
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH')}
    env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    exe=package/'zynq-etm-bridge.exe'
    checked=subprocess.run([str(exe),'--check','--data-dir',str(out/'check')],env=env,capture_output=True,text=True,encoding='utf8',timeout=60)
    if checked.returncode:raise ValueError('EXE preflight failed: '+checked.stdout+checked.stderr)
    (out/'preflight.json').write_text(json.dumps(json.loads(checked.stdout),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    log=(out/'server.log').open('w',encoding='utf8')
    process=subprocess.Popen([str(exe),'--port',str(a.port),'--data-dir',str(out/'data'),'--offline','--no-browser'],
        env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    url='http://127.0.0.1:'+str(a.port)
    def request(path,body=None,content_type='application/json'):
        data=json.dumps(body).encode('utf8') if body is not None and content_type=='application/json' else body
        with urlopen(Request(url+path,data=data,headers={'Content-Type':content_type}),timeout=30) as response:
            return response.read()
    def api(path,body=None):return json.loads(request('/etm/api/'+path,body))
    report={'hardwareAccess':False,'hardwareRoutesDisabled':True,'pythonOnPath':False,'nodeOnPath':False,
        'package':str(package),'sourceRevision':manifest['sourceRevision'],'packageFilesVerified':len(manifest['files']),'records':[]}
    passed=False
    try:
        deadline=time.monotonic()+30
        while True:
            try:health=api('health');break
            except (OSError,ValueError):
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('EXE startup failed; see '+str(out/'server.log'))
                time.sleep(.1)
        assert health['decodeEngineProfile']['name']=='native' and health['frontend']['vectorized']
        # Prove this is our isolated child before importing any fixture. A port
        # collision must never send test records to another running workbench.
        launcher=json.loads(request('/etm-launcher.json'))
        state=json.loads((out/'data/bridge-state.json').read_text(encoding='utf8'))
        assert process.poll() is None and state['pid']==process.pid
        assert launcher['bootId']==state['bootId'] and launcher['offline'] is True
        assert launcher['dataDirectory']==str((out/'data').resolve())
        assert launcher['packageId']==hashlib.sha256((package/'package-manifest.json').read_bytes()).hexdigest()
        report['health']=health
        for path in ['/native-probe/usb/devices','/native-probe/hid/devices','/native-probe/serial/devices','/etm/api/capture']:
            try:request(path,{})
            except HTTPError as error:assert error.code==403,(path,error.code)
            else:raise AssertionError('Hardware route was enabled: '+path)
        fixtures=ROOT/'tools/tests/fixtures'
        f103=io.BytesIO()
        with zipfile.ZipFile(f103,'w',zipfile.ZIP_DEFLATED) as archive:
            for name in ('session.json','capture.bin','sources.json'):
                archive.write(fixtures/'etm-offline'/name,name)
            archive.write(ROOT/'prebuilt/golden/f103ze-cdc48.elf','firmware.elf')
        rows=[('F103ZE',f103.getvalue(),5467740),('H743',(fixtures/'h743-etmv4/h743.etmrecord').read_bytes(),210497)]
        for name,data,expected in rows:
            boundary='bridge-'+uuid.uuid4().hex
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="capture"; filename="reference.etmrecord"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode())
            saved=json.loads(request('/etm/api/import',body,'multipart/form-data; boundary='+boundary))
            sid=saved['record'];started=time.perf_counter();job=api('decode/'+sid,{})['job']
            deadline=time.monotonic()+120
            while True:
                state=api('jobs/'+job)
                if state['state'] in ('done','error'):break
                if time.monotonic()>deadline:raise TimeoutError('Decode timeout: '+name)
                time.sleep(.1)
            assert state['state']=='done',state
            seconds=time.perf_counter()-started
            overview=api('browse/'+sid+'/overview')
            assert overview['summary']['instructions']==expected,overview['summary']
            assert overview['summary']['packetIssues']==0,overview['summary']
            api('browse/'+sid+'/page?view=events&offset=913&limit=20')
            api('browse/'+sid+'/window?fromSeq=913&toSeq=977&bins=64')
            svg=request('/etm/api/download/'+sid+'/flame-svg?mode=timeline&weight=records&fromSeq=913&toSeq=977')
            assert ET.fromstring(svg).tag=='{http://www.w3.org/2000/svg}svg'
            (out/(name+'-flame.svg')).write_bytes(svg)
            folder=out/'data/records'/sid
            assert (folder/'store/manifest.json').is_file()
            assert not (folder/'events.jsonl').exists() and not (folder/'native.jsonl').exists()
            report['records'].append({'target':name,'record':sid,'decodeSeconds':seconds,'summary':overview['summary'],
                'flameBytes':len(svg),'traceStore':True,'perInstructionJsonl':False})
        # Launching it twice must reopen the existing instance, not spawn a second server.
        duplicate=subprocess.run([str(exe),'--port',str(a.port),'--data-dir',str(out/'data'),'--offline','--no-browser'],env=env,capture_output=True,timeout=30)
        assert duplicate.returncode==0,duplicate.stderr
        report.update(ok=True,pid=process.pid,port=a.port,duplicateLaunchReused=True)
        passed=True
    finally:
        if not passed or not a.keep_running:
            process.terminate();process.wait(timeout=15)
        log.close()
        report['keptRunning']=bool(passed and a.keep_running)
        (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
