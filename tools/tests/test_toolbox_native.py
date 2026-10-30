import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'etm-service/tools'))


class NativeWebCaptureTests(unittest.TestCase):
    def test_auth_reservation_restore_and_stop_without_killing_transaction(self):
        from werkzeug.test import Client as WsgiClient
        from werkzeug.wrappers import Response
        import native_web_capture
        class Client(WsgiClient):
            def open(self, *args, **kwargs):
                kwargs.setdefault('environ_overrides', {})['REMOTE_ADDR'] = '127.0.0.1'
                return super().open(*args, **kwargs)
        spec = importlib.util.spec_from_file_location('native_web_test_service', ROOT / 'web/tools/dev/serve-etm.py')
        service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(service)
        pair = ROOT / 'prebuilt/20261030_orbtrace_oversample_parser'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            token = folder / 'token'
            token.write_text('b' * 64)
            application = service.create_application(ROOT / 'etm-service', ROOT / 'web', token,
                (pair / 'orbtrace_oversample_parser.bit', pair / 'zynqdap_orbtrace.elf'))
            capture = application.mounts['/etm'].extensions['native_capture']
            backend = capture.backend
            backend.RECORDS = folder / 'records'
            backend.RECORDS.mkdir()
            elf_id = 'elf-' + 'c' * 32
            target = backend.directory(elf_id)
            target.mkdir()
            shutil.copy2(ROOT / 'etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf', target / 'firmware.elf')
            client = Client(application, Response)
            headers = {'X-Trace-CLI': 'b' * 64}
            options = {'elfId': elf_id, 'seconds': .01, 'decode': False}
            self.assertEqual(client.post('/etm/api/native-capture', json=options).status_code, 403)
            self.assertEqual(client.post('/etm/api/native-capture', headers=headers,
                json={**options, 'seconds': 2}).status_code, 400)
            with patch.object(native_web_capture.threading, 'Thread'):
                response = client.post('/etm/api/native-capture', headers=headers, json=options)
                self.assertEqual(response.status_code, 200, response.data)
                job = response.json
                self.assertEqual(client.post('/etm/api/native-capture', headers=headers, json=options).status_code, 400)

            restored = True
            def transaction(command, **kwargs):
                self.assertNotIn('timeout', kwargs, 'must not kill before target restoration')
                raw = Path(command[command.index('--out') + 1])
                raw.mkdir()
                (raw / 'capture.bin').write_bytes(b'actual bytes')
                (raw / 'target-before.json').write_text('{"etmcr":123}')
                (raw / 'acceptance.json').write_text(json.dumps({'restored': restored}))
                (raw / 'session.json').write_text(json.dumps({'config': {'protocol': 'ETMv3', 'traceid': 2},
                                                             'quality': {'loss': False}}))
                return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr='')

            prepared = {'seconds': .01, 'decode': False, 'traceId': 2, 'hclkDiv': 4, 'gpioSpeed': 1, 'swdKhz': 1000}
            with patch.object(native_web_capture.subprocess, 'run', side_effect=transaction) as run:
                capture.run(job['job'], job['record'], prepared)
                self.assertEqual(run.call_count, 1)
            self.assertEqual(backend.jobs[job['job']]['state'], 'done')
            self.assertTrue(backend.meta(job['record'])['targetVerified'])
            self.assertNotIn('_laLease', backend.jobs[job['job']])

            with patch.object(native_web_capture.threading, 'Thread'):
                cancelled = client.post('/etm/api/native-capture', headers=headers, json=options).json
            stop = client.post('/etm/api/stop/' + cancelled['job'], headers=headers)
            self.assertTrue(stop.json['restorePending'])
            with patch.object(native_web_capture.subprocess, 'run') as run:
                capture.run(cancelled['job'], cancelled['record'], prepared)
                run.assert_not_called()
            self.assertEqual(backend.jobs[cancelled['job']]['state'], 'cancelled')

            with patch.object(native_web_capture.threading, 'Thread'):
                failed = client.post('/etm/api/native-capture', headers=headers, json=options).json
            restored = False
            with patch.object(native_web_capture.subprocess, 'run', side_effect=transaction):
                capture.run(failed['job'], failed['record'], prepared)
            self.assertEqual(backend.jobs[failed['job']]['state'], 'error')
            self.assertTrue(backend.jobs[failed['job']]['cleanupPending'])
            self.assertEqual(client.post('/etm/api/native-capture', headers=headers, json=options).status_code, 400)


if __name__ == '__main__':
    unittest.main()
