import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from engine_profile import activate_native_profile,current_profile


class EngineProfileTests(unittest.TestCase):
    def test_product_profile_overrides_inherited_legacy_flags(self):
        with patch.dict(os.environ,{'ETM_STORE_WRITE':'0','ETM_STORE_ENGINE':'python',
                                     'ETM_NATIVE_FORMAT':'text','ETM_STORE_ENGINE_FALLBACK':'1'}):
            result=activate_native_profile()
            self.assertEqual(result['name'],'native')
            self.assertFalse(result['perInstructionJsonl'])
            from decode_stream import store_write_enabled,native_format
            from trace_store_write import resolve_engine,engine_fallback_enabled
            self.assertTrue(store_write_enabled())
            self.assertEqual(native_format(),'binary')
            self.assertEqual(resolve_engine(),'native')
            self.assertFalse(engine_fallback_enabled())
            self.assertEqual(os.environ['ETM_QUERY_ENGINE'],'native')
            self.assertEqual(os.environ['ETM_EXPORT_ENGINE'],'native')

    def test_runtime_diagnostics_do_not_label_a_legacy_profile_native(self):
        with patch.dict(os.environ,{'ETM_STORE_WRITE':'0','ETM_NATIVE_FORMAT':'text'}):
            self.assertEqual(current_profile()['name'],'custom')


if __name__=='__main__':unittest.main()
