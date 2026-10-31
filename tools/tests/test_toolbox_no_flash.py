import unittest
from unittest.mock import patch
from tools.f103_no_flash_web_acceptance import NoFlash
from tools.f103_stream_acceptance import Streams

class NoFlashTests(unittest.TestCase):
    def test_no_flash_suite_refuses_programming_before_dispatch(self):
        instance=object.__new__(NoFlash)
        with patch.object(Streams,'call') as dispatched:
            for payload in [dict(action='probe-flash'),dict(action='flash'),
                            dict(action='workbench',page='flash',op='click',selector='#f-flash'),
                            dict(action='workbench',page='flash',op='invoke',method='flash')]:
                with self.assertRaises(ValueError):instance.call(payload)
            with self.assertRaises(ValueError):instance.flash()
            dispatched.assert_not_called()

    def test_no_flash_suite_preserves_readonly_state_inspection(self):
        instance=object.__new__(NoFlash)
        with patch.object(Streams,'call',return_value={'checked':True}) as dispatched:
            self.assertEqual(instance.call(dict(action='workbench',page='flash',op='describe')),{'checked':True})
            dispatched.assert_called_once()

if __name__=='__main__':unittest.main()
