import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import probe_load


class ProbeLoadTests(unittest.TestCase):
    def test_default_plan_does_not_load_or_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'plan'
            stdout = io.StringIO()
            with patch.object(probe_load, 'execute') as execute, contextlib.redirect_stdout(stdout):
                self.assertEqual(probe_load.main(['--dry-run', '--out', str(out)]), 0)
            execute.assert_not_called()
            self.assertFalse(out.exists())

        plan = json.loads(stdout.getvalue())
        files = plan['files']
        self.assertEqual(plan['operation'], 'JTAG/RAM')
        self.assertEqual(plan['commands']['load'][5:8],
                         [files[key]['path'] for key in ('zynq_elf', 'bit', 'ps_init')])
        self.assertEqual(plan['commands']['verify'][5], files['zynq_elf']['path'])

    def test_target_mcu_elf_rejected_before_hardware(self):
        elf = probe_load.ROOT / 'prebuilt/golden/f103ze-cdc48.elf'
        bit = probe_load.RELEASE / 'probe.bit'
        init = probe_load.RELEASE / 'ps7_init.tcl'
        with patch.object(probe_load, 'execute') as execute, contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as result:
                probe_load.main(['--bit', str(bit), '--zynq-elf', str(elf), '--ps-init', str(init)])
        self.assertEqual(result.exception.code, 2)
        self.assertIn('fit in low OCM', stderr.getvalue())
        execute.assert_not_called()

    def test_idle_check_rejects_running_dma(self):
        session = Mock()
        session.run.return_value = (
            'LOAD_STATE LEVEL_SHIFTERS 0000000f\nLOAD_STATE FPGA_RESET 00000000\n'
            'LOAD_STATE CAPTURE 00000000\nLOAD_STATE SWD 00000000\n'
            'LOAD_STATE DDR 00000000\nLOAD_STATE CDMA 00000000\n'
        )
        with self.assertRaisesRegex(RuntimeError, 'DMA'):
            probe_load.probe_state(session)

    def test_idle_check_accepts_pl_isolation_without_pl_status(self):
        session = Mock()
        session.run.return_value = 'LOAD_STATE LEVEL_SHIFTERS 00000000\nLOAD_STATE FPGA_RESET 0000000f\n'
        self.assertEqual(probe_load.probe_state(session), {'LEVEL_SHIFTERS': '0x0', 'FPGA_RESET': '0xf'})
