import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import toolbox
from tools.toolbox_catalog import full_catalog


class ToolboxTests(unittest.TestCase):
    def test_catalog_only_contains_shipped_pages_and_controls(self):
        catalog = full_catalog(ROOT, toolbox.catalog())
        self.assertEqual(len(catalog['pages']), 9)
        for page in catalog['pages']:
            self.assertTrue((ROOT / page['source']).is_file())
            self.assertGreater(len(page['controls']), 0)
        selectors = {p['id']: {c['selector'] for c in p['controls']} for p in catalog['pages']}
        self.assertIn('#start', selectors['etm'])
        self.assertNotIn('#start', selectors['serial'])
        self.assertIn('#f-flash', selectors['flash'])
        self.assertNotIn('#f-flash', selectors['gen'])

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
            self.assertEqual(client.get('/').status_code, 200)
            embedded = client.get('/etm/?embedded=1')
            self.assertEqual(embedded.status_code, 200)
            self.assertIn(b'data-api-base="/etm/api/"', embedded.data)
            self.assertIn(b'data-embedded="1"', embedded.data)
            self.assertEqual(client.get('/etm/integration.json').json['backend'], 'zynq')
            self.assertEqual(client.get('/etm/api/health').status_code, 200)
            self.assertEqual(client.get('/etm/app/view.js').status_code, 200)
            self.assertEqual(client.get('/.git/config').status_code, 404)
            self.assertEqual(client.post('/trace-cli/request', json={'action': 'ping'}).status_code, 403)
            headers = {'X-Trace-CLI': 'a' * 64}
            self.assertEqual(client.post('/trace-cli/request', headers=headers, json={'action': 'ping'}).status_code, 409)
            self.assertEqual(client.post('/trace-cli/request', headers={**headers, 'Origin': 'https://example.com'}, json={'action': 'ping'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
