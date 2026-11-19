"""A report write failure must never skip either level of hardware recovery."""
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jtag200_f103_fixture as fixture
import jtag200_f103_sweep as sweep


class JtagFixtureRecovery(unittest.TestCase):
    def test_target_restore_after_final_report_failure(self):
        mem = Mock()
        mem.read.return_value = bytes(fixture.SIZE)
        mem.word.return_value = 1 << 17
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(out=Path(tmp)/'run', restore=False)
            with patch.object(fixture, 'low_link', return_value=nullcontext(mem)), \
                 patch.object(fixture, 'elf_contents', return_value=('ARM', [])), \
                 patch.object(fixture, 'snapshot', return_value={}), \
                 patch.object(fixture, 'save', side_effect=[None, OSError('save'), OSError('final save')]), \
                 patch.object(fixture, 'restore') as restore:
                with self.assertRaisesRegex(OSError, 'final save'):
                    fixture.run(args)
                restore.assert_called_once()
                self.assertEqual(restore.call_args.args[0], args.out.resolve())

    def test_probe_reload_after_final_report_failure(self):
        original = bytes(fixture.SIZE)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            state = dict(ram_sha256=sha256(original).hexdigest(), tap=hex(fixture.TAP),
                         hclk_mhz=128, guards=[0, 0])
            (folder/'state.json').write_text(json.dumps(state))
            (folder/'backup.bin').write_bytes(original)
            mem = Mock()
            mem.word.return_value = 1 << 17
            mem.read.side_effect = [original, sweep.PATTERN]
            with patch.object(sweep, 'low_link', return_value=nullcontext(mem)), \
                 patch.object(sweep, 'guards', return_value=[0, 0]), \
                 patch.object(sweep, 'Ownership'), patch.object(sweep, 'Session'), \
                 patch.object(sweep, 'check_streams'), patch.object(sweep, 'probe_state'), \
                 patch.object(sweep, 'load_pair', side_effect=RuntimeError('load')), \
                 patch.object(sweep, 'write_report', side_effect=OSError('final save')), \
                 patch.object(sweep.subprocess, 'run') as reload:
                args = SimpleNamespace(fixture=folder, sdk=folder, server='unused', cable_serial='test')
                with self.assertRaisesRegex(OSError, 'final save'):
                    sweep.main(args)
                reload.assert_called_once()
                self.assertIn('probe-load', reload.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
