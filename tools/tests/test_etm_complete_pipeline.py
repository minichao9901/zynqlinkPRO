"""Real native build failures must preserve the last published trace generation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'etm-service/tools'))
import decode_stream
import native_complete
import native_storebuild
import trace_store as ts
from trace_cli import engine_environment


class CompletePipelineTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {})
        self.environment.start()
        engine_environment()
        os.environ.update(ETM_COMPLETE_INDEX='1', ETM_DIRECT_DECODE='1', ETM_BUFFERED_DECODE='1')
        scratch = ROOT / 'build'
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='complete-index-test-', dir=scratch)
        self.folder = Path(self.temporary.name)
        fixture = ROOT / 'tools/tests/fixtures/etm-offline'
        for name in ('session.json', 'sources.json'):
            shutil.copy2(fixture / name, self.folder / name)
        shutil.copy2(ROOT / 'prebuilt/golden/f103ze-cdc48.elf', self.folder / 'firmware.elf')
        self.raw = (fixture / 'capture.bin').read_bytes()[:4096]
        (self.folder / 'capture.bin').write_bytes(self.raw)
        self.config = json.loads((fixture / 'session.json').read_text(encoding='utf8'))['config']

    def tearDown(self):
        self.temporary.cleanup()
        self.environment.stop()

    def decode(self):
        return decode_stream.decode_stream(self.raw, self.folder / 'firmware.elf', self.folder,
            config=self.config, sources=json.loads((self.folder / 'sources.json').read_text(encoding='utf8')))

    def published(self):
        return {name: (self.folder / name).read_bytes() for name in ('decoded.json', 'sources.json', 'store/manifest.json')}

    def test_native_mode_has_no_python_data_writer(self):
        import native_facts_index
        with patch.object(native_facts_index, 'build_full_index', side_effect=AssertionError('Python index called')), \
                patch.object(ts._BlockSink, 'assemble', side_effect=AssertionError('Python writer called')):
            self.decode()
        with ts.TraceStore(self.folder / 'store', verify='full') as store:
            self.assertEqual(store.manifest['queryIndex']['builtBy'], 'native-complete-index')
            self.assertEqual(len(store.query_index.arrays._archive.files) - 1, 60)
            self.assertTrue(store.container.optional_features & ts.QUERY_INDEX_FEATURE)

    def test_manifest_failure_rolls_back_metadata(self):
        self.decode()
        before = self.published()
        with patch.object(ts, '_publish_manifest', side_effect=OSError('injected publish failure')):
            with self.assertRaisesRegex(OSError, 'injected publish failure'):
                self.decode()
        self.assertEqual(self.published(), before)
        with ts.TraceStore(self.folder / 'store', verify='full') as store:
            self.assertGreater(store.counts['instructions'], 0)

    def test_cleanup_failure_keeps_committed_generation(self):
        self.decode()
        before = self.published()['store/manifest.json']
        with patch.object(ts, '_remove_tree', side_effect=OSError('injected cleanup failure')):
            with self.assertRaisesRegex(OSError, 'injected cleanup failure'):
                self.decode()
        self.assertNotEqual(self.published()['store/manifest.json'], before)
        with ts.TraceStore(self.folder / 'store', verify='full') as store:
            self.assertGreater(store.counts['instructions'], 0)

    def test_same_length_store_corruption_prevents_publication(self):
        self.decode()
        before = self.published()
        original = native_complete.publish
        def corrupt(record_dir, store_dir, directory, *args, **kwargs):
            path = directory / 'store.bin'
            with path.open('r+b') as stream:
                stream.seek(-1, 2)
                byte = stream.read(1)
                stream.seek(-1, 2)
                stream.write(bytes([byte[0] ^ 1]))
            return original(record_dir, store_dir, directory, *args, **kwargs)
        with patch.object(native_complete, 'publish', side_effect=corrupt):
            with self.assertRaisesRegex(ts.TraceStoreError, 'SHA'):
                self.decode()
        self.assertEqual(self.published(), before)

    def test_native_json_roundtrip_matches_python_format(self):
        result = subprocess.run([str(native_storebuild.binary_path()), '--self-test-json-format'],
                                capture_output=True, check=True, timeout=30)
        text = result.stdout.decode('utf8').strip()
        value = json.loads(text)
        self.assertEqual(len(value['values']), 10008)
        self.assertEqual(text, json.dumps(value, ensure_ascii=False))

    def test_binary_only_record_uses_native_processed_bytes(self):
        import trace_store_write
        os.environ['ETM_DIRECT_DECODE'] = '0'
        original = self.decode()
        self.assertTrue((self.folder / 'native.bin').is_file())
        (self.folder / 'etm.bin').unlink()
        (self.folder / 'capture.bin').unlink()
        result, decoded = trace_store_write.write(self.folder, self.folder / 'store',
            native_bin=self.folder / 'native.bin', elf=self.folder / 'firmware.elf',
            config=self.config, write_decoded=True)
        self.assertTrue(result['ok'])
        self.assertEqual(decoded['inputBytes'], original['status']['processed'])
        self.assertEqual(decoded['summary'], original['summary'])
        self.assertEqual(decoded['quality'], original['quality'])


if __name__ == '__main__':
    unittest.main()
