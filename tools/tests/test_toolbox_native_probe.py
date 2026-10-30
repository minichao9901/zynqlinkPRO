import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'etm-service/tools'))
from native_probe import NativeProbe, install


class NativeProbeTests(unittest.TestCase):
    def test_http_redelivery_returns_the_original_result_without_hardware_reexecution(self):
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/'token';token.write_text('c'*64)
            proxy=NativeProbe(SimpleNamespace(),token)
            calls=[]
            def operation():
                calls.append('USB write/read')
                return ({'ok':True,'value':{'data':'real USB reply'}},200)
            identity='a'*32;body={'action':'write','data':'abc'}
            first=proxy.deliver(identity,body,operation)
            self.assertEqual(proxy.deliver(identity,body,operation),first)
            self.assertEqual(len(calls),1)
            with self.assertRaisesRegex(ValueError,'内容不一致'):
                proxy.deliver(identity,{'action':'reset'},operation)
            del proxy.delivery_cache[identity]
            with self.assertRaisesRegex(ValueError,'拒绝重放'):
                proxy.deliver(identity,body,operation)
            self.assertEqual(len(calls),1)

    def test_loopback_token_and_origin_are_required_before_hardware_dispatch(self):
        from flask import Flask
        app = Flask('native_probe_test')
        backend = SimpleNamespace(app=Flask('backend'), lock=threading.RLock(), jobs={}, ACTIVE=('queued', 'starting'))
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / 'token'; token.write_text('c' * 64)
            proxy = install(app, backend, token)
            with app.test_client() as client, patch.object(proxy, 'usb_call', return_value=[{'realTransport': True}]) as hardware:
                self.assertEqual(client.post('/native-probe/usb/list', json={}).status_code, 403)
                headers = {'X-Trace-CLI': 'c' * 64}
                self.assertEqual(client.post('/native-probe/usb/list', json={}, headers={**headers, 'Origin': 'https://example.com'}).status_code, 403)
                hardware.assert_not_called()
                result = client.post('/native-probe/usb/list', json={}, headers=headers)
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.json['value'][0]['realTransport'])

    def test_other_owner_cannot_close_an_active_usb_session(self):
        backend = SimpleNamespace(lock=threading.RLock(), jobs={}, ACTIVE=('queued',))
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / 'token'; token.write_text('c' * 64)
            proxy = NativeProbe(backend, token)
            device = object(); proxy.usb = device; proxy.usb_owner = 'a' * 32
            self.assertEqual(proxy.usb_call('close', {'owner': 'b' * 32}), {'closed': True})
            self.assertIs(proxy.usb, device)
            with self.assertRaisesRegex(ValueError, '另一Web会话'):
                proxy.usb_call('open', {'owner': 'b' * 32})
            backend.jobs['capture'] = {'kind': 'capture', 'state': 'queued'}
            with self.assertRaisesRegex(ValueError, 'ETM'):
                proxy.usb_call('open', {'owner': 'a' * 32})

    def test_binary_limits_and_capture_cleanup_guard(self):
        with self.assertRaises(Exception):
            NativeProbe.blob('not base64')
        with self.assertRaises(ValueError):
            NativeProbe.blob('YWI=', 1)
        self.assertEqual(NativeProbe.blob('AID/'), bytes([0, 128, 255]))


if __name__ == '__main__':
    unittest.main()
