"""Native ownership, legacy reader compatibility and generation isolation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import subprocess
import random
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'etm-service/tools'))
import decode_stream
import native_core
import native_storebuild
import trace_store as ts
import trace_store_index
from trace_cli import engine_environment


class NativeCoreTests(unittest.TestCase):
    def test_failed_worker_start_closes_log_and_registers_no_session(self):
        log = tempfile.TemporaryFile('w+b')
        before = set(native_core._CLIENTS)
        with patch.object(native_core.tempfile, 'TemporaryFile', return_value=log), \
                patch.object(native_core.subprocess, 'Popen', side_effect=OSError('injected start failure')):
            with self.assertRaisesRegex(OSError, 'injected start failure'):
                native_core.Client('query-server', 'unused')
        self.assertTrue(log.closed)
        self.assertEqual(set(native_core._CLIENTS), before)

    def setUp(self):
        self.environment = patch.dict(os.environ, {})
        self.environment.start()
        engine_environment()
        os.environ.update(ETM_NATIVE_STATIC='1', ETM_NATIVE_QUERY='1', ETM_COMPLETE_INDEX='1')
        self.temp = tempfile.TemporaryDirectory(prefix='native-core-test-', dir=ROOT / 'build')
        self.folder = Path(self.temp.name)
        fixture = ROOT / 'tools/tests/fixtures/etm-offline'
        for name in ('session.json', 'sources.json'):
            shutil.copy2(fixture / name, self.folder / name)
        shutil.copy2(ROOT / 'prebuilt/golden/f103ze-cdc48.elf', self.folder / 'firmware.elf')
        self.raw = (fixture / 'capture.bin').read_bytes()[:4096]
        (self.folder / 'capture.bin').write_bytes(self.raw)
        self.config = json.loads((fixture / 'session.json').read_text(encoding='utf8'))['config']

    def tearDown(self):
        self.temp.cleanup()
        self.environment.stop()

    def decode(self):
        return decode_stream.decode_stream(self.raw, self.folder / 'firmware.elf', self.folder,
            config=self.config, sources=json.loads((self.folder / 'sources.json').read_text(encoding='utf8')))

    def test_no_python_elf_static_or_store_parser_in_native_workflow(self):
        import decode_trace
        import static_dict
        def forbidden(*args, **kwargs):
            raise AssertionError('Python ELF/static/store parser entered the native workflow')
        with patch.object(decode_trace.Image, '_parse', forbidden), \
                patch.object(static_dict, 'build_static_entries', forbidden), \
                patch.object(ts._Container, '__init__', forbidden):
            decoded = self.decode()
            with native_core.Store(self.folder / 'store') as store:
                self.assertEqual(store.meta['record']['protocol'], self.config['protocol'])
                self.assertEqual(store.overview()['summary'], decoded['summary'])
                self.assertEqual(store.event(913)['event']['seq'], 913)
                self.assertTrue(store.window(900, 977)['timeline'])

    def test_native_reader_accepts_legacy_npz_index(self):
        self.decode()
        with patch.dict(os.environ, {'ETM_NATIVE_QUERY': '0'}):
            trace_store_index.reencode_store_index(self.folder / 'store', container='v1')
        with ts.TraceStore(self.folder / 'store') as reference, native_core.Store(self.folder / 'store') as native:
            self.assertEqual(native.event(913), reference.event(913))
            self.assertEqual(native.window(900, 977), reference.window(900, 977))
            self.assertEqual(native.stats()['queryIndex']['container'], 'v1')

    def test_reader_reconstructs_missing_index_inside_cpp(self):
        self.decode()
        with ts.TraceStore(self.folder / 'store') as store:
            expected = store.window(900, 977)
            manifest = dict(store.manifest)
            sink = ts._BlockSink(self.folder / 'without-index.payload')
            try:
                for n, block in enumerate(store.container.blocks):
                    if block.block_type != ts.BLK_QUERY:
                        sink.add_raw(block.block_type, store.container.raw_block(n), block.count, block.flags)
                output = self.folder / 'without-index.bin'
                info = sink.assemble(output, int(manifest['generationTag'], 0),
                                     required_features=store.container.required_features)
            finally:
                sink.close()
        destination = self.folder / 'store/generations' / manifest['generation'] / 'store.bin'
        os.replace(output, destination)
        manifest['files'] = [dict(name='store.bin', **info)]
        ts._publish_manifest(self.folder / 'store', manifest)
        with native_core.Store(self.folder / 'store') as native:
            self.assertEqual(native.window(900, 977), expected)

    def test_crc_corruption_is_not_hidden_by_updated_outer_sha(self):
        self.decode()
        with ts.TraceStore(self.folder / 'store') as store:
            manifest = store.manifest
            block = store.container.blocks[store.container.of_type(ts.BLK_META)[0]]
            offset = block.offset
        path = self.folder / 'store/generations' / manifest['generation'] / 'store.bin'
        with path.open('r+b') as handle:
            handle.seek(offset)
            value = handle.read(1)
            handle.seek(offset)
            handle.write(bytes([value[0] ^ 1]))
        manifest['files'][0]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        ts._publish_manifest(self.folder / 'store', manifest)
        with self.assertRaisesRegex(ts.TraceStoreError, 'CRC'):
            native_core.Store(self.folder / 'store')

    def test_native_reindex_preserves_old_reader_generation(self):
        self.decode()
        with native_core.Store(self.folder / 'store') as old:
            expected = old.event(913)
            prior = old.generation
            result = native_core.reindex(self.folder / 'store')
            self.assertTrue(result['ok'])
            self.assertNotEqual(prior, result['generation'])
            self.assertEqual(old.event(913), expected)
            with native_core.Store(self.folder / 'store') as current:
                self.assertEqual(current.event(913), expected)

    def test_native_reindex_can_write_legacy_v1(self):
        self.decode()
        result = native_core.reindex(self.folder / 'store', container='v1')
        self.assertTrue(result['ok'])
        with ts.TraceStore(self.folder / 'store') as reference, native_core.Store(self.folder / 'store') as native:
            self.assertEqual(native.window(900, 977), reference.window(900, 977))
            self.assertEqual(native.stats()['queryIndex']['container'], 'v1')

    def test_native_image_matches_reference_and_keeps_flash_policy(self):
        import decode_trace
        with patch.dict(os.environ, {'ETM_NATIVE_STATIC': '0'}):
            reference = decode_trace.Image(self.folder / 'firmware.elf')
        image = native_core.Image(self.folder / 'firmware.elf')
        try:
            self.assertEqual(image.functions, reference.functions)
            self.assertEqual(image.lines, reference.lines)
            for address, _, _ in reference.functions[:8]:
                self.assertEqual(image.location(address), reference.location(address))
            self.assertEqual(image.elf_info()['sha256'], hashlib.sha256(image.bytes).hexdigest())
        finally:
            image.close()

    def test_fault_names_use_actual_protocol(self):
        import native_binary
        completed = subprocess.run([str(native_storebuild.binary_path()), 'fault-name-test'], capture_output=True, check=True)
        names = json.loads(completed.stdout)['names']
        for protocol, values in names.items():
            for code, name in values.items():
                self.assertEqual(name, native_binary.packet_name(int(code), protocol))

    def test_native_unicode_lower_matches_python(self):
        values = ['ΟΣ', 'ΟΣΑ', 'İSTANBUL', 'Σ\u0301', 'AΣ\u0301', '中文ABC', 'ẞÄÖ', '𐐀ABC']
        rng = random.Random(1201)
        for _ in range(500):
            chars = []
            for _ in range(7):
                cp = rng.randrange(0x110000)
                if not 0xD800 <= cp <= 0xDFFF:
                    chars.append(chr(cp))
            values.append(''.join(chars))
        path = self.folder / 'text.json'
        path.write_text(json.dumps(values, ensure_ascii=False), encoding='utf8')
        result = subprocess.run([str(native_storebuild.binary_path()), 'text-test', str(path)], capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)['lower'], [v.lower() for v in values])


if __name__ == '__main__':
    unittest.main()
