"""Protect the accepted bytes and the strictly offline dependency check."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

class ReleaseLayoutTests(unittest.TestCase):
    def test_golden_and_recovery_match_accepted_identity(self):
        expected={
            'prebuilt/golden/probe.bit':'1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473',
            'prebuilt/golden/application.elf':'e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c',
            'prebuilt/golden/f103ze-cdc48.elf':'e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f',
            'prebuilt/recovery/BOOT.bin':'ee7116bc71b0c7f0fdbebed75c5c85137e80ec7ef7c1b8cc3db50cebb39f1185',
        }
        for path,digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)

    def test_offline_doctor_neither_probes_usb_nor_calls_service(self):
        spec=importlib.util.spec_from_file_location('offline_release_trace',ROOT/'etm-service/trace.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module,'zynq_status',side_effect=AssertionError('USB was probed')),patch('urllib.request.urlopen',side_effect=AssertionError('network called')),contextlib.redirect_stdout(io.StringIO()) as output:
            result=module.doctor(['--offline'])
        self.assertEqual(result,0)
        data=json.loads(output.getvalue())
        self.assertTrue(data['ok'])
        self.assertTrue(data['result']['offline'])

if __name__=='__main__':unittest.main()
