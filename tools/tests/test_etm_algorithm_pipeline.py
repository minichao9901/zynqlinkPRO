"""Algorithm and failure-path checks; no USB, target or board access."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'etm-service/tools'))
import issue_runs
import native_storebuild as native
import trace_store as ts
from trace_store_adapter import capture_start_from_store


class CompactIssuesTests(unittest.TestCase):
    def setUp(self):
        self.value = dict(format=issue_runs.FORMAT, reasons=['IT unknown', 'no sync'],
            predicates=[[2, 3, 100], [5, 5, 104]], boundaries=[[0, 0, 1], [2, 100, 1]],
            extra=[dict(category='packet', offset=105, reason='tail')], total=5)

    def test_lossless_order_and_reasons(self):
        rows = issue_runs.unpack(json.loads(json.dumps(self.value)))
        self.assertEqual([(r.get('startSeq'), r['category']) for r in rows],
                         [(0, 'boundary'), (2, 'boundary'), (2, 'predicate'), (5, 'predicate'), (None, 'packet')])
        self.assertEqual(rows[2], dict(category='predicate', startSeq=2, endSeq=3,
                                      records=2, offset=100, reason='IT unknown'))

    def test_invalid_groups_fail_explicitly(self):
        cases = [dict(total=4), dict(predicates=[[3, 2, 0]]),
                 dict(boundaries=[[0, 0, -1]]), dict(predicates=[[True, 3, 0]]),
                 dict(extra=[42]), dict(reasons=[])]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ts.TraceStoreError):
                issue_runs.unpack(dict(self.value, **change))

    def test_required_feature_and_unknown_feature(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for feature, allowed in [(ts.ISSUE_RUNS_FEATURE, True), (4, False)]:
                sink = ts._BlockSink(root / 'payload')
                try:
                    sink.add_compressed_json(ts.BLK_ISSUES, self.value)
                    sink.assemble(root / 'store.bin', 7, required_features=feature)
                finally:
                    sink.close()
                container = ts._Container.__new__(ts._Container)
                try:
                    if allowed:
                        container.__init__(root / 'store.bin', ts.FILE_TRACE, 7)
                        self.assertEqual(container.required_features, feature)
                        self.assertEqual(issue_runs.unpack(json.loads(container.block(0))), issue_runs.unpack(self.value))
                    else:
                        with self.assertRaises(ts.TraceStoreError):
                            container.__init__(root / 'store.bin', ts.FILE_TRACE, 7)
                finally:
                    if hasattr(container, '_handle'):
                        container.close()


@patch.dict('os.environ', {'ETM_NATIVE_QUERY': '0'})
class CaptureStartIndexTests(unittest.TestCase):
    def make_store(self):
        return SimpleNamespace(meta=dict(captureStartIndex=dict(version=1, firstRecoveredSeq=2,
            firstRecoveredPC=0x1000, staticPcsAreRecovered=True)), summary=dict(firstSeq=2),
            static=[SimpleNamespace(pc=0x1000), SimpleNamespace(pc=0x2000)],
            event=Mock(return_value=dict(event=dict(pc=0x1000))),
            navigate=Mock(return_value=dict(seq=9)), close=Mock())

    def test_prepared_index_avoids_execution_block_decode(self):
        store = self.make_store()
        with patch('trace_store_adapter.trace_store.TraceStore', return_value=store):
            result = capture_start_from_store('store', dict(captureEntry=0x2000))
        self.assertEqual(result, dict(selectedPC=0x2000, firstRecoveredPC=0x1000,
                                      entryRecovered=True, firstMatchesEntry=False))
        store.event.assert_not_called()
        store.navigate.assert_not_called()
        store.close.assert_called_once()

    def test_legacy_and_invalid_metadata(self):
        store = self.make_store()
        store.meta = {}
        with patch('trace_store_adapter.trace_store.TraceStore', return_value=store):
            self.assertTrue(capture_start_from_store('store', dict(captureEntry=0x1000))['firstMatchesEntry'])
        store.event.assert_called_once_with(2)
        store = self.make_store()
        store.meta['captureStartIndex']['firstRecoveredSeq'] = 3
        with patch('trace_store_adapter.trace_store.TraceStore', return_value=store), self.assertRaises(ts.TraceStoreError):
            capture_start_from_store('store', dict(captureEntry=0x1000))
        store.close.assert_called_once()


# Exercise the actual process ownership/handshake implementation with a tiny
# subprocess, rather than mocking away timeout, exit and cleanup behavior.
FAKE_WORKER = r'''
import argparse, json, pathlib, struct, sys, time
p=argparse.ArgumentParser()
for name in ['static','prepare-static','ranges-out','json','owner-pid','mode']:p.add_argument('--'+name)
a=p.parse_args()
if a.mode=='no-ready':time.sleep(30)
pathlib.Path(a.ranges_out).write_bytes(b'R2RANGES1'+struct.pack('<QQIII',1,1,4096,4098,1))
pathlib.Path(a.prepare_static).write_text(json.dumps({'rangeInstructions':1,'etmSha256':'unused'}))
while not pathlib.Path(a.static+'.ready').exists():time.sleep(.01)
if pathlib.Path(a.static).read_bytes()==b'bad':
 print('invalid dictionary',file=sys.stderr);sys.exit(3)
pathlib.Path(a.json).write_text(json.dumps({'ok':True}))
'''


class PreparedBuildOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.script = self.root / 'worker.py'
        self.script.write_text(FAKE_WORKER, encoding='utf8')
        self.static = self.root / 'static.bin'
        self.children = []
        self.real_popen = native.subprocess.Popen

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.kill(); child.wait(timeout=5)
        self.temp.cleanup()

    def start(self, mode='ready', timeout=5):
        def capture(*args, **kwargs):
            child = self.real_popen(*args, **kwargs)
            self.children.append(child)
            return child
        with patch.object(native, 'probe', return_value=dict(capabilities=['typed-replay-v1'])), \
                patch.object(native.subprocess, 'Popen', side_effect=capture):
            return native.PreparedBuild([str(self.script), '--static', str(self.static), '--mode', mode],
                dict(ready=self.root / 'ready.json', ranges=self.root / 'ranges.bin'), self.static,
                binary=sys.executable, timeout=timeout)

    def test_successful_handshake(self):
        session = self.start()
        self.static.write_bytes(b'valid')
        self.assertTrue(session.finish()['ok'])
        self.assertIsNotNone(session.process.poll())
        self.assertTrue(session.log.closed)

    def test_invalid_dictionary_is_not_published(self):
        session = self.start()
        self.static.write_bytes(b'bad')
        with self.assertRaisesRegex(native.NativeStorebuildError, 'invalid dictionary'):
            session.finish()
        self.assertFalse(session.result.exists())
        self.assertIsNotNone(session.process.poll())
        self.assertTrue(session.log.closed)

    def test_cancel_and_timeout_release_process(self):
        session = self.start()
        session.abort()
        session.abort()  # idempotent cleanup
        self.assertIsNotNone(session.process.poll())
        (self.root / 'ready.json').unlink()
        with self.assertRaisesRegex(native.NativeStorebuildError, 'timed out'):
            self.start('no-ready', timeout=.2)
        self.assertTrue(all(child.poll() is not None for child in self.children))


if __name__ == '__main__':
    unittest.main()
