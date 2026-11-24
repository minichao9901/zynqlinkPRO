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

    def test_selectio_alias_previews_exact_manifest_pair(self):
        root=probe_load.ROOT/'prebuilt/selectio-usb-split-raw4-20261123'
        expected=json.loads((root/'manifest.json').read_text(encoding='utf8'))['hashes']
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'unused'
            stdout=io.StringIO()
            with patch.object(probe_load,'execute') as execute,contextlib.redirect_stdout(stdout):
                self.assertEqual(probe_load.main(['--selectio','--dry-run','--out',str(out)]),0)
            actual={Path(v['path']).name:v['sha256'] for v in json.loads(stdout.getvalue())['files'].values()}
            self.assertEqual(actual,expected)
            execute.assert_not_called()
            self.assertFalse(out.exists())

    def test_pair_directory_checks_manifest_before_hardware(self):
        root = probe_load.ROOT / 'prebuilt/selectio-spi-cdc-phase-drift-20261123'
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf8'))
        with tempfile.TemporaryDirectory() as directory:
            pair = Path(directory)
            for name in manifest['hashes']:
                (pair / name).write_bytes((root / name).read_bytes())
            (pair / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
            stdout = io.StringIO()
            with patch.object(probe_load, 'execute') as execute, contextlib.redirect_stdout(stdout):
                self.assertEqual(probe_load.main(['--pair', str(pair), '--dry-run']), 0)
            actual = {Path(v['path']).name: v['sha256'] for v in json.loads(stdout.getvalue())['files'].values()}
            self.assertEqual(actual, manifest['hashes'])
            execute.assert_not_called()
            (pair / 'ps7_init.tcl').write_bytes(b'changed')
            stderr = io.StringIO()
            with patch.object(probe_load, 'execute') as execute, contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as result:
                    probe_load.main(['--pair', str(pair)])
            self.assertEqual(result.exception.code, 2)
            self.assertIn('SHA-256', stderr.getvalue())
            self.assertIn('ps7_init.tcl', stderr.getvalue())
            execute.assert_not_called()

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
