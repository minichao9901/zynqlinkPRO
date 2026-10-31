import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('zynq_doctor_test',ROOT/'etm-service/trace.py')
trace=importlib.util.module_from_spec(spec);spec.loader.exec_module(trace)

class Response:
    status=200
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return json.dumps({'decodeEngineProfile':{'name':'native','perInstructionJsonl':False}}).encode()

class DoctorTests(unittest.TestCase):
    def run_doctor(self,mismatch=False):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);bit=folder/'probe.bit';elf=folder/'app.elf'
            bit.write_bytes(b'bit identity');elf.write_bytes(b'elf identity')
            data={'protocol':'workbench/1','status':'serving','url':'http://127.0.0.1:12345','nativeCapture':
                  {'bit':str(bit),'bitSha256':hashlib.sha256(bit.read_bytes()).hexdigest(),
                   'elf':str(elf),'elfSha256':'0'*64 if mismatch else hashlib.sha256(elf.read_bytes()).hexdigest()}}
            (folder/'toolbox-runtime.json').write_text(json.dumps(data))
            stream=io.StringIO()
            with patch.object(trace,'zynq_status',return_value={'ok':True}),patch('urllib.request.urlopen',return_value=Response()) as opened,contextlib.redirect_stdout(stream):
                code=trace.doctor(['--runtime',str(folder)])
            self.assertEqual(opened.call_args.args[0],'http://127.0.0.1:12345/etm/api/health')
            return code,json.loads(stream.getvalue())

    def test_doctor_uses_unified_service_and_declared_pair(self):
        code,payload=self.run_doctor()
        self.assertEqual(code,0);self.assertTrue(payload['result']['checks']['pair']['ok'])
        self.assertTrue(payload['result']['checks']['nativeProfile']['ok'])

    def test_changed_pair_is_not_reported_as_matching_runtime(self):
        code,payload=self.run_doctor(mismatch=True)
        self.assertEqual(code,3);self.assertFalse(payload['result']['checks']['pair']['ok'])

    def test_missing_runtime_returns_structured_error(self):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):code=trace.doctor(['--runtime',str(ROOT/'missing-runtime-for-test')])
        self.assertEqual(code,2);self.assertFalse(json.loads(stream.getvalue())['ok'])

if __name__=='__main__':unittest.main()
