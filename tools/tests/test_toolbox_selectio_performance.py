import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
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

    def test_calibration_trims_the_pass_interval_without_losing_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = SimpleNamespace(out=Path(temporary) / "calibration", serial="mock")
            profile = performance.CAL_POINTS[0]

            def run(command, log):
                output = Path(command[command.index("--out") + 1])
                tap = int(command[command.index("--tap") + 1])
                slot = int(command[command.index("--slot") + 1])
                passed = slot == profile.slot and abs(tap-profile.tap) <= 2
                report = dict(passed=passed, restored=True, error=None if passed else "mock ACK",
                              windows=[{"clock": {"wire_hz": 49_999_999}}] if passed else [])
                output.mkdir()
                (output / "result.json").write_text(json.dumps(report), encoding="utf-8")
                return int(not passed)

            with patch.object(performance, "run", side_effect=run):
                self.assertEqual(performance.calibrate(profile, args), 0)
            report = json.loads((args.out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(report["recommended"], {"tap": 8, "slot": 24, "idle": 0})
            self.assertEqual(len(report["probes"]), 9)
            self.assertEqual(sum(row["passed"] for row in report["probes"]), 5)
            self.assertTrue(all(row["restored"] for row in report["probes"]))

    def test_high_hclk_adds_standard_sram_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            args = SimpleNamespace(out=folder / "output", pair=folder / "pair", serial="mock",
                                   seconds=60, rounds=3)
            point = next(point for point in performance.POINTS if point.name == "DBG-08")
            commands = {}

            def run(command, log):
                commands[log.name] = command
                if log.name in ("cmsis-peak.log", "rtt-cdc.log"):
                    output = command[command.index("--output") + 1]
                    Path(output).write_text('{"restore_match": true, "registers_match": true}', encoding="utf-8")
                return 0

            with patch.object(performance, "run", side_effect=run):
                self.assertEqual(performance.inside_clock_guard(point, args), 0)
            standard = commands["cmsis-peak.log"]
            self.assertEqual(standard[standard.index("--transport") + 1], "jtag")
            self.assertEqual(standard[standard.index("--speed-hz") + 1], 100_000_000)
            self.assertEqual(standard[standard.index("--words") + 1:standard.index("--repeats") + 2],
                             [512, "--depth", 32, "--loops", 256, "--repeats", 3])
            self.assertIn("rtt-cdc.log", commands)
            self.assertIn("hss.log", commands)

    def test_failed_rtt_prevents_hss_route_change_even_with_sram_restored(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            args = SimpleNamespace(out=folder / "output", pair=folder / "pair", serial="mock",
                                   seconds=60, rounds=3)
            point = next(point for point in performance.POINTS if point.name == "DBG-03")
            commands = []

            def run(command, log):
                commands.append(log.name)
                if log.name == "rtt-cdc.log":
                    output = command[command.index("--output") + 1]
                    Path(output).write_text('{"restore_match": true, "registers_match": true}', encoding="utf-8")
                    return 1
                return 0

            with patch.object(performance, "run", side_effect=run):
                self.assertEqual(performance.inside_clock_guard(point, args), 1)
            self.assertIn("rtt-cdc.log", commands)
            self.assertNotIn("hss.log", commands)

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
