import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
from werkzeug.test import Client as WsgiClient


class LocalClient(WsgiClient):
    def open(self,*args,**kwargs):
        kwargs.setdefault('environ_overrides',{})['REMOTE_ADDR']='127.0.0.1'
        return super().open(*args,**kwargs)

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.zynq_bridge import application,locations


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch=ROOT/'build/bridge-validation'
        cls.scratch.mkdir(parents=True,exist_ok=True)
    def app(self,data,offline=False):
        data.mkdir(exist_ok=True);token=data/'token';token.write_text('d'*64)
        _,backend,web,service,helpers=locations()
        return application(backend,web,service,helpers,data,token,offline=offline)

    def test_offline_mode_blocks_all_hardware_and_uses_external_user_data(self):
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        with tempfile.TemporaryDirectory(dir=self.scratch) as folder,patch.dict(os.environ),patch('usb.core.find',side_effect=AssertionError('USB forbidden')) as usb:
            data=Path(folder);app=self.app(data,offline=True);client=LocalClient(app,Response)
            headers={'X-Trace-CLI':'d'*64}
            for path in ['/native-probe/usb/devices','/native-probe/hid/devices','/native-probe/serial/devices','/etm/api/capture']:
                self.assertEqual(client.post(path,json={},headers=headers).status_code,403,path)
            self.assertEqual(client.get('/etm/api/status').status_code,403)
            with client.get('/') as response:
                self.assertIn('离线验收',response.get_data(as_text=True))
            with client.get('/etm/api/health') as response:
                self.assertTrue(response.json['decoder']);self.assertTrue(response.json['nativeIndexer'])
                self.assertEqual(response.json['decodeEngineProfile']['name'],'native')
            self.assertTrue((data/'records').is_dir());usb.assert_not_called()

    def test_tutorial_example_is_readonly_and_available_without_hardware(self):
        import base64,hashlib
        from werkzeug.wrappers import Response
        with tempfile.TemporaryDirectory(dir=self.scratch) as folder,patch.dict(os.environ),patch('usb.core.find',side_effect=AssertionError('USB forbidden')) as usb:
            data=Path(folder);client=LocalClient(self.app(data,offline=True),Response)
            before=list((data/'records').iterdir())
            with client.get('/etm/api/tutorial-example') as response:
                self.assertEqual(response.status_code,200)
                example=base64.b64decode(response.json['base64'])
                self.assertEqual(hashlib.sha256(example).hexdigest(),response.json['sha256'])
                self.assertEqual(example,(ROOT/'tools/tests/fixtures/h743-etmv4/h743.etmrecord').read_bytes())
                self.assertIn('不是当前板卡',response.json['source'])
            with client.get('/etm/?embedded=1') as response:
                page=response.get_data(as_text=True)
                self.assertEqual(page.count('id="tutorials"'),1)
                self.assertIn('embedded-actions',page)
                self.assertGreater(page.index('id="tutorials"'),page.index('class="embedded-actions"'))
            self.assertEqual(list((data/'records').iterdir()),before)
            usb.assert_not_called()

    def test_web_capture_api_replays_both_protocols_through_real_native_decode(self):
        """Only external LA/USB is replaced. Upload, capture job, C++ and browse run."""
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        h743=ROOT/'tools/tests/fixtures/h743-etmv4'
        with zipfile.ZipFile(h743/'h743.etmrecord') as archive:
            hfiles={n:archive.read(n) for n in archive.namelist()}
        f=ROOT/'tools/tests/fixtures/etm-offline'
        rows=[('F103ZE',(ROOT/'prebuilt/golden/f103ze-cdc48.elf').read_bytes(),(f/'capture.bin').read_bytes(),json.loads((f/'session.json').read_text(encoding='utf8'))['config'],5467740),
              ('H743',hfiles['firmware.elf'],hfiles['capture.bin'],json.loads(hfiles['session.json'])['config'],210497)]
        rows += [(flag,hfiles['firmware.elf'],hfiles['capture.bin'],json.loads(hfiles['session.json'])['config'],None) for flag in ('loss','unsynced','unfinished')]
        with tempfile.TemporaryDirectory(dir=self.scratch) as folder,patch.dict(os.environ),patch('usb.core.find',side_effect=AssertionError('USB forbidden')) as usb:
            app=self.app(Path(folder));client=LocalClient(app,Response);backend=sys.modules['etm_toolbox_backend']
            with client.post('/etm/api/capture',json={'hclkDiv':4}) as rejected:
                self.assertEqual(rejected.status_code,400)
            for label,elf,raw,config,instructions in rows:
                calls=[]
                class Sock:
                    def settimeout(self,value):pass
                    def sendall(self,value):calls.append(value)
                    def recv(self,n):return b'ACK'
                    def shutdown(self,how):pass
                class ReplayLA:
                    def __init__(self):self.sock=Sock()
                    def cmd(self,text,timeout=None):
                        if text=='get-supported-sample-rate':return '500000000'
                        if text=='get-actual-sample-depth':return '5000000'
                        if text=='get-actual-sample-time':return '.01'
                        return 'OK'
                    def close(self):pass
                def export(vis,path,channels):
                    Path(path).write_bytes(raw)
                    vis.capture_quality={'loss':False,'synced':True,'ended':True,'fclk':120000000,'tckKhz':1000}
                    if label=='loss':vis.capture_quality['loss']=True
                    if label=='unsynced':vis.capture_quality['synced']=False
                    if label=='unfinished':vis.capture_quality['ended']=False
                with patch.object(backend,'Vis',ReplayLA),patch.object(backend,'do_export',export):
                    with client.post('/etm/api/elf',data={'elf':(io.BytesIO(elf),label+'.elf')}) as upload:
                        self.assertEqual(upload.status_code,200,upload.data);elf_id=upload.json['elfId']
                    with client.post('/etm/api/capture',json={'elfId':elf_id,'config':config,'rate':500000000,'seconds':.01,'sync':True,'decode':True,'targetVerified':True,'libraryOrigin':'validation'}) as response:
                        self.assertEqual(response.status_code,200,response.data);job=response.json
                    deadline=time.monotonic()+90
                    while (backend.jobs[job['job']]['state'] not in ('done','error') or backend.jobs[job['job']].get('_laLease')) and time.monotonic()<deadline:time.sleep(.05)
                    self.assertEqual(backend.jobs[job['job']]['state'],'done' if instructions else 'error',backend.jobs[job['job']])
                self.assertEqual(calls,[b'start'])
                record=Path(folder)/'records'/job['record']
                metadata=json.loads((record/'session.json').read_text(encoding='utf8'))
                self.assertIsNone(metadata['actualDepth']);self.assertIsNone(metadata['actualTime'])
                self.assertIsNone(metadata['captureExtent']['actualSamples'])
                self.assertIsNone(metadata['captureExtent']['actualSeconds'])
                self.assertIsNone(metadata['captureExtent']['complete'])
                self.assertFalse(metadata['captureExtent']['sampleCountMeasured'])
                if instructions is None:
                    record=Path(folder)/'records'/job['record']
                    self.assertEqual((record/'capture.bin').read_bytes(),raw)
                    self.assertFalse((record/'decoded.json').exists())
                    self.assertIn('loss=',backend.jobs[job['job']]['error'])
                    if label=='loss':
                        with client.post('/etm/api/decode/'+job['record'],json={}) as response:
                            redecoded=response.json['job']
                        deadline=time.monotonic()+60
                        while backend.jobs[redecoded]['state'] not in ('done','error') and time.monotonic()<deadline:time.sleep(.05)
                        self.assertEqual(backend.jobs[redecoded]['state'],'done',backend.jobs[redecoded])
                        saved=json.loads((record/'session.json').read_text(encoding='utf8'))
                        self.assertEqual(saved['errorStage'],'capture')
                        self.assertEqual(saved['captureStatus'],'failed')
                        with client.get('/etm/api/browse/'+job['record']+'/overview') as response:
                            self.assertTrue(response.json['captureQuality']['loss'])
                            self.assertTrue(response.json['recordError'])
                        backend.browse_store(job['record']).close()
                    continue
                with client.get('/etm/api/browse/'+job['record']+'/overview') as response:
                    self.assertEqual(response.status_code,200,response.data)
                    self.assertEqual(response.json['summary']['instructions'],instructions)
                    self.assertEqual(response.json['summary']['packetIssues'],0)
                    self.assertTrue(response.json['captureQuality']['ended'])
                record=Path(folder)/'records'/job['record']
                self.assertTrue((record/'store/manifest.json').is_file())
                self.assertFalse((record/'events.jsonl').exists());self.assertFalse((record/'native.jsonl').exists())
                backend.browse_store(job['record']).close()
            usb.assert_not_called()

    def test_zynq_export_keeps_duration_and_transport_proof_before_usb_release(self):
        import zynq_la
        session=SimpleNamespace(wait=lambda timeout:True,error=None,bytes=b'trace',seconds=1,
            quality={'hostSeconds':1.003,'loss':False,'synced':True,'ended':True},diagnostics=lambda:{'implemented':False})
        with tempfile.TemporaryDirectory() as folder,patch.object(zynq_la,'session',return_value=session),patch.object(zynq_la,'release') as release:
            vis=zynq_la.Vis();zynq_la.do_export(vis,Path(folder)/'capture.bin',[])
            self.assertEqual(vis.seconds,1);self.assertEqual(vis.capture_quality,session.quality)
            self.assertEqual(float(vis.cmd('get-actual-sample-time')),1.003)
            release.assert_called_once()

    def test_ddr_hardware_extent_and_raw_record_roundtrip(self):
        from werkzeug.wrappers import Response
        with tempfile.TemporaryDirectory(dir=self.scratch) as folder,patch.dict(os.environ),patch('usb.core.find',side_effect=AssertionError('USB forbidden')):
            app=self.app(Path(folder),offline=True);client=LocalClient(app,Response);backend=sys.modules['etm_toolbox_backend']
            transport=dict(transport='ddr-usb/1',hardwareTicks=400000000,requestedTicks=400000000,
                refClockHz=200000000,hardwareSeconds=2,hostSeconds=3.5,stopReason=0,loss=False)
            extent=backend.capture_extent(None,500000000,2,transport)
            self.assertEqual(extent['actualSeconds'],2);self.assertTrue(extent['complete'])
            self.assertIsNone(extent['actualSamples']);self.assertFalse(extent['sampleCountMeasured'])
            broken={**transport,'hardwareSeconds':3.5}
            with self.assertRaises(ValueError):backend.capture_extent(None,500000000,2,broken)
            sid='capture-'+'d'*32;record=backend.directory(sid);record.mkdir()
            record.joinpath('firmware.elf').write_bytes((ROOT/'prebuilt/golden/f103ze-cdc48.elf').read_bytes())
            record.joinpath('capture.bin').write_bytes(b'ETM')
            record.joinpath('capture.frm1').write_bytes(bytes(range(16)))
            record.joinpath('ddr-capture.json').write_text(json.dumps(transport))
            backend.save(sid,dict(input='capture.bin',config=json.loads((ROOT/'tools/tests/fixtures/etm-offline/session.json').read_text())['config']))
            with client.get('/etm/api/download/'+sid+'/record') as response:
                self.assertEqual(response.status_code,200,response.data)
                package=response.data
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                self.assertEqual(archive.read('capture.frm1'),bytes(range(16)))
                self.assertEqual(json.loads(archive.read('ddr-capture.json')),transport)
            with client.post('/etm/api/import',data={'capture':(io.BytesIO(package),'ddr.etmrecord')}) as response:
                self.assertEqual(response.status_code,200,response.data)
                imported=backend.directory(response.json['record'])
            self.assertEqual((imported/'capture.frm1').read_bytes(),bytes(range(16)))
            self.assertEqual(json.loads((imported/'ddr-capture.json').read_text()),transport)


if __name__=='__main__':unittest.main()
