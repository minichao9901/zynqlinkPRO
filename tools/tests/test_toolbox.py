import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import toolbox
from tools.toolbox_catalog import full_catalog


class ToolboxTests(unittest.TestCase):
    def test_expired_worker_can_transfer_only_unclaimed_read_only_jobs(self):
        from flask import Flask
        spec = importlib.util.spec_from_file_location('queue_test', ROOT / 'etm-service/tools/web_cli_queue.py')
        queue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(queue)
        for action, claim, expected in [('describe',False,200), ('describe',True,409), ('click',False,409)]:
            with self.subTest(action=action, claimed=claim), tempfile.TemporaryDirectory() as directory:
                clock = SimpleNamespace(now=100)
                with patch.object(queue,'time',SimpleNamespace(monotonic=lambda:clock.now)), \
                     patch.object(queue.threading.Condition,'wait',return_value=False):
                    app = Flask(__name__)
                    path = Path(directory) / 'token'
                    queue.install_web_cli(app,path)
                    client = app.test_client()
                    headers = {'X-Trace-CLI':path.read_text()}
                    old, new = {'worker':'a'*32}, {'worker':'b'*32}
                    poll = lambda value: client.post('/trace-cli/poll',headers=headers,json=value)
                    self.assertEqual(poll(old).status_code,200)
                    job = client.post('/trace-cli/request',headers=headers,json={
                        'action':'workbench','op':action,'page':'dbg',
                    }).json['id']
                    if claim:
                        self.assertEqual(poll(old).json['job']['id'],job)
                    self.assertEqual(poll(new).status_code,409)
                    clock.now += 16
                    self.assertFalse(client.get('/trace-cli/health',headers=headers).json['ready'])
                    result = poll(new)
                    self.assertEqual(result.status_code,expected)
                    if expected == 200:
                        self.assertEqual(result.json['job']['id'],job)

    def test_catalog_only_contains_shipped_pages_and_controls(self):
        catalog = full_catalog(ROOT, toolbox.catalog())
        self.assertEqual(len(catalog['pages']), 8)
        for page in catalog['pages']:
            self.assertTrue((ROOT / page['source']).is_file())
            self.assertGreater(len(page['controls']), 0)
        selectors = {p['id']: {c['selector'] for c in p['controls']} for p in catalog['pages']}
        self.assertIn('#start', selectors['etm'])
        self.assertNotIn('#start', selectors['serial'])
        self.assertIn('#f-flash', selectors['flash'])
        self.assertNotIn('gen', selectors)
        self.assertNotIn('#f-backend', selectors['flash'])
        self.assertNotIn('#r-backend', selectors['rtt'])

    def test_file_arguments_preserve_binary_content(self):
        import base64
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'target.bin'
            file.write_bytes(bytes([0, 128, 255]))
            result = toolbox.expand_arguments([{'$file': str(file), 'kind': 'buffer'}])[0]
            self.assertEqual(base64.b64decode(result['$base64']), file.read_bytes())
            with self.assertRaises(ValueError):
                toolbox.expand_arguments({'$file': str(file), 'kind': 'eval'})

    def test_runtime_rejects_non_loopback_and_invalid_token(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            state = folder / 'toolbox-runtime.json'
            state.write_text(json.dumps({'url': 'http://example.com'}))
            with self.assertRaises(ValueError):
                toolbox.Client(folder)
            state.write_text(json.dumps({'url': 'http://127.0.0.1:8878'}))
            (folder / 'cli-token').write_text('bad')
            with self.assertRaises(ValueError):
                toolbox.Client(folder)

    def test_unified_service_mounts_etm_and_requires_queue_token(self):
        from werkzeug.test import Client as WsgiClient
        from werkzeug.wrappers import Response
        class Client(WsgiClient):
            def open(self, *args, **kwargs):
                kwargs.setdefault('environ_overrides', {})['REMOTE_ADDR'] = '127.0.0.1'
                return super().open(*args, **kwargs)
        spec = importlib.util.spec_from_file_location('toolbox_test_service', ROOT / 'web/tools/dev/serve-etm.py')
        service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(service)
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'token'
            token.write_text('a' * 64)
            client = Client(service.create_application(ROOT / 'etm-service', ROOT / 'web', token), Response)
            with client.get('/') as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'data-etm-base="/etm"', response.data)
            embedded = client.get('/etm/?embedded=1')
            self.assertEqual(embedded.status_code, 200)
            self.assertIn(b'data-api-base="/etm/api/"', embedded.data)
            self.assertIn(b'data-embedded="1"', embedded.data)
            self.assertIn(b'__etmPageErrors', embedded.data)
            self.assertEqual(client.get('/etm/integration.json').json['backend'], 'zynq')
            self.assertEqual(client.get('/etm/api/health').status_code, 200)
            self.assertEqual(client.get('/etm/api/health').json['decodeEngineProfile']['name'],'native')
            self.assertEqual(client.get('/etm-launcher.json').json['decodeEngineProfile']['settings']['ETM_NATIVE_FORMAT'],'binary')
            with client.get('/etm/app/view.js') as response:
                self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get('/.git/config').status_code, 404)
            self.assertEqual(client.post('/trace-cli/request', json={'action': 'ping'}).status_code, 403)
            headers = {'X-Trace-CLI': 'a' * 64}
            self.assertEqual(client.post('/trace-cli/request', headers=headers, json={'action': 'ping'}).status_code, 409)
            self.assertEqual(client.post('/trace-cli/request', headers={**headers, 'Origin': 'https://example.com'}, json={'action': 'ping'}).status_code, 403)
            wid='b'*32
            client.post('/trace-cli/poll',headers=headers,json={'worker':wid})
            jid=client.post('/trace-cli/request',headers=headers,json={'action':'ping'}).json['id']
            claimed=client.post('/trace-cli/poll',headers=headers,json={'worker':wid}).json
            self.assertEqual(claimed['job']['id'],jid)
            done={'worker':wid,'result':{'ok':True,'value':{'once':1}}}
            self.assertEqual(client.post('/trace-cli/complete/'+jid,headers=headers,json=done).status_code,200)
            self.assertEqual(client.post('/trace-cli/complete/'+jid,headers=headers,json=done).status_code,200)
            done['result']['value']['once']=2
            self.assertEqual(client.post('/trace-cli/complete/'+jid,headers=headers,json=done).status_code,409)


if __name__ == '__main__':
    unittest.main()
