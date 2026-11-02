"""A preserved derivative cannot replace or weaken consumed-input bindings."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'etm-service/tools'))
from trace_store_adapter import verify_inputs


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'etm.bin').write_bytes(b'raw trace')
        (self.root / 'native.bin').write_bytes(b'unused legacy derivation')
        self.raw_sha = hashlib.sha256(b'raw trace').hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self):
        return dict(bindings=dict(inputs={'etm.bin': dict(bytes=9, sha256=self.raw_sha)},
            sourceInput=dict(kind='etm', recordFile='etm.bin', sha256=self.raw_sha),
            unconsumedDerivedInputs=['native.bin']))

    def test_unused_native_is_explicitly_excluded(self):
        report = verify_inputs(self.root, self.manifest())
        self.assertTrue(report['verified'])
        self.assertEqual(report['excluded'], ['native.bin'])
        self.assertEqual(report['blockingHashed'], 1)
        (self.root / 'native.bin').write_bytes(b'different unused file')
        self.assertTrue(verify_inputs(self.root, self.manifest())['verified'])

    def test_changed_raw_is_still_rejected(self):
        (self.root / 'etm.bin').write_bytes(b'new trace')  # identical length
        report = verify_inputs(self.root, self.manifest())
        self.assertFalse(report['verified'])
        self.assertTrue(any('etm.bin' in problem for problem in report['problems']))

    def test_explicit_native_binding_wins_over_ignore_marker(self):
        manifest = self.manifest()
        data = (self.root / 'native.bin').read_bytes()
        manifest['bindings']['inputs']['native.bin'] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        (self.root / 'native.bin').write_bytes(bytes([data[0] ^ 1]) + data[1:])
        report = verify_inputs(self.root, manifest)
        self.assertFalse(report['verified'])
        self.assertTrue(any('native.bin' in problem for problem in report['problems']))

    def test_unhashed_inputs_never_become_verified(self):
        manifest = self.manifest()
        manifest['bindings']['inputs']['etm.bin']['sha256'] = None
        report = verify_inputs(self.root, manifest)
        self.assertFalse(report['verified'])
        self.assertIn('etm.bin', report['unverified'])
        self.assertNotIn('native.bin', report['excluded'])


if __name__ == '__main__':
    unittest.main()
