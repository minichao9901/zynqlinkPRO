import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import selectio_f103_performance as performance


class SelectioPerformanceTests(unittest.TestCase):
    def test_selected_preview_leaves_hardware_and_output_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "unused"
            argv = ["performance", "--pair", temporary, "--out", str(output),
                    "--only", "DBG-08", "--only", "ETM-02"]
            stdout = io.StringIO()
            with patch("sys.argv", argv), patch.object(performance, "run") as run, \
                    contextlib.redirect_stdout(stdout):
                self.assertEqual(performance.main(), 0)
            run.assert_not_called()
            self.assertFalse(output.exists())
        plan = json.loads(stdout.getvalue())
        self.assertEqual([p["name"] for p in plan["points"]], ["DBG-08"])
        self.assertEqual(plan["points"][0]["idle"], 29)
        self.assertEqual(plan["seconds"], 60)
        self.assertEqual(plan["rounds"], 3)
        self.assertEqual(plan["etm36_rounds"], 3)
        self.assertFalse(plan["swd50_historical"])

    def test_unconfirmed_recovery_stops_before_the_next_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            pair = Path(temporary) / "pair"
            pair.mkdir()
            hashes = {"application.elf": "test-elf"}
            (pair / "manifest.json").write_text(json.dumps({"hashes": hashes}), encoding="utf-8")
            output = Path(temporary) / "results"
            commands = []

            def run(command, log):
                commands.append(log.name)
                if log.name == "load.log":
                    proof = output / "load/ocm/result.json"
                    proof.parent.mkdir(parents=True)
                    proof.write_text(json.dumps(dict(passed=True, elf_sha256="test-elf",
                                                     expected_executable_bytes=1)), encoding="utf-8")
                    return 0
                folder = output / "DBG-04-guard"
                folder.mkdir()
                (folder / "state.json").write_text(json.dumps({"restored": False, "probe_hashes": hashes}),
                                                   encoding="utf-8")
                return 1

            argv = ["performance", "--pair", str(pair), "--out", str(output), "--only", "DBG-04",
                    "--only", "DBG-08", "--execute"]
            with patch("sys.argv", argv), patch.object(performance, "run", side_effect=run), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "DBG-04: target recovery"):
                    performance.main()
            self.assertEqual(commands, ["load.log", "DBG-04.log"])
            record = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertFalse(record["complete"])
            self.assertFalse(record["rows"][0]["restored"])


if __name__ == "__main__":
    unittest.main()
