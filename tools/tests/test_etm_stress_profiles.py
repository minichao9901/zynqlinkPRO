import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.stress_etm_web import arguments


class StressProfiles(unittest.TestCase):
    def args(self,*extra):
        return arguments(['--runtime','unused','--artifacts','unused',*extra])

    def test_h743_requires_its_firmware_and_explicit_echo_port_before_any_hardware(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):self.args('--profile','stm32h743')
            with tempfile.TemporaryDirectory() as folder:
                elf=Path(folder)/'h743.elf';elf.write_bytes(b'argument-only fixture')
                with self.assertRaises(SystemExit):
                    self.args('--profile','stm32h743','--elf',str(elf),'--functions','main,trace_hook_entry','--echo')
                a=self.args('--profile','stm32h743','--elf',str(elf),'--functions','main,trace_hook_entry',
                    '--echo','--cdc-port','COM99','--hse-mhz','25','--reset-before')
                self.assertEqual(a.elf,str(elf));self.assertIsNone(a.sources)
                self.assertEqual(a.hse_mhz,25);self.assertEqual(a.cdc_port,'COM99');self.assertTrue(a.reset_before)

    def test_f103_defaults_remain_separate(self):
        a=self.args()
        self.assertEqual(a.profile,'stm32f103ze');self.assertEqual(a.hse_mhz,8)
        self.assertEqual(a.functions,'cdc_poll,cdc_tx_poll');self.assertFalse(a.reset_before)
        self.assertEqual(Path(a.elf).name,'f103ze-cdc48.elf')


if __name__=='__main__':unittest.main()
