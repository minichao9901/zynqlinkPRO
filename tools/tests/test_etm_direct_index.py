"""Sequence mapping must preserve events, including consecutive boundary events."""
import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'etm-service/tools'))
from trace_store_index import QueryIndex
import trace_store as ts


class SequenceMappingTests(unittest.TestCase):
    def check_layout(self, events, length):
        index = QueryIndex.__new__(QueryIndex)
        index.event_seqs = np.asarray(events, dtype=np.int64)
        expected = np.asarray([i for i in range(length) if i not in set(events)])
        np.testing.assert_array_equal(index.seq_of_insn(np.arange(len(expected))), expected)
        for ordinal, seq in enumerate(expected):
            self.assertEqual(int(index.seq_of_insn(ordinal)), int(seq))

    def test_consecutive_events_and_empty_events(self):
        for events in ([], [0, 1], [0, 1, 3, 4, 7, 8, 9], [9]):
            self.check_layout(events, 10)

    def test_random_event_placements(self):
        rng = np.random.default_rng(991)
        for _ in range(100):
            length = int(rng.integers(1, 400))
            events = np.flatnonzero(rng.random(length) < .5).tolist()
            self.check_layout(events, length)

    def test_large_sequence_values(self):
        index = QueryIndex.__new__(QueryIndex)
        index.event_seqs = np.asarray([0, 1, 2**40, 2**40 + 1], np.int64)
        np.testing.assert_array_equal(index.seq_of_insn([0, 2**40 - 2, 2**40 - 1]),
                                      [2, 2**40 + 2, 2**40 + 3])


class IssueBlockTests(unittest.TestCase):
    def test_issue_limit_is_separate_and_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(ts, 'MAX_BLOCK_BYTES', 1024), patch.object(ts, 'MAX_ISSUE_BYTES', 4096):
                sink = ts._BlockSink(folder / 'payload')
                try:
                    sink.add_compressed_json(ts.BLK_ISSUES, ['x' * 2048], level=1)
                    sink.assemble(folder / 'store.bin', 123)
                finally:
                    sink.close()
                container = ts._Container(folder / 'store.bin', ts.FILE_TRACE, 123)
                try:
                    self.assertGreater(len(container.block(0)), 1024)
                    with patch.object(ts, 'MAX_ISSUE_BYTES', 1024):
                        container._cache.clear()
                        with self.assertRaises(ts.TraceStoreError):
                            container.block(0)
                finally:
                    container.close()
                sink = ts._BlockSink(folder / 'oversized')
                try:
                    with self.assertRaises(ts.TraceStoreError):
                        sink.add_compressed_json(ts.BLK_ISSUES, ['x' * 8192])
                    with self.assertRaises(ts.TraceStoreError):
                        sink.add_compressed_json(ts.BLK_META, ['x' * 2048])
                finally:
                    sink.close()


if __name__ == '__main__':
    unittest.main()
