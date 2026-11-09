"""The legacy H7 input contract must also work with the native builder."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'etm-service/tools'))
from decode_trace import decoder_config, DEFAULT_CONFIG


class EtmConfigContract(unittest.TestCase):
    def test_legacy_h7_config_has_explicit_native_protocol_without_mutation(self):
        original = dict(DEFAULT_CONFIG)
        result = decoder_config(original)
        self.assertEqual(result['protocol'], 'ETMv4')
        self.assertEqual({k: result[k] for k in original}, original)
        self.assertNotIn('protocol', original)

    def test_protocol_validation_remains_strict(self):
        with self.assertRaisesRegex(ValueError, '不支持'):
            decoder_config({'protocol': 'ETMv5'})
        with self.assertRaisesRegex(ValueError, '缺少寄存器'):
            decoder_config({'protocol': 'ETMv3'})


if __name__ == '__main__':
    unittest.main()
