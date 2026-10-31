import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import etm_ddr_physical_capture as capture


class CaptureIdentity(unittest.TestCase):
    def test_stale_nonce_is_rejected_before_any_ddr_payload_read(self):
        class Physical:
            calls=[]
            def __init__(self,session): pass
            def read_words(self,address,count):
                words=[0]*34
                words[0]=0x45444d31;words[11]=7;words[12:14]=[0x10000000,0x30000000]
                return words
            def run(self,body):
                self.calls.append(body)
                marker=re.search(r'set f \[open \{([^}]+)\}',body)[1]
                Path(marker).write_text(json.dumps(dict(armBeforeMs=1000,activeObservedMs=1001)))
                Path(marker).rename(Path(marker).with_suffix(''))
                words=[0]*34
                words[2]=2;words[10]=1;words[31]=10;words[33]=2
                return 'TRACE_DDR_REGS '+' '.join(map(str,words))
        scratch=ROOT/'build/ddr-host-tests';scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp, \
             patch.object(capture,'reservation',return_value=(0x10000000,0x30000000)), \
             patch.object(capture,'PhysicalMemory',Physical), \
             patch.object(capture,'live_clock_snapshot',return_value={'FCLK_Hz':120000000}), \
             patch.object(capture.secrets,'randbits',return_value=9):
            with self.assertRaisesRegex(RuntimeError,'identity mismatch'):
                capture.capture(temp,ROOT/'prebuilt/golden/application.elf',1,200000000,lambda:None)
            report=json.loads((Path(temp)/'ddr/result.json').read_text())
            self.assertFalse(report['passed']);self.assertTrue(report['workerRetired'])
            self.assertEqual(len(Physical.calls),1)
            self.assertNotIn('-bin',Physical.calls[0])

    def test_diagnostic_clock_override_cannot_enter_ddr_acceptance(self):
        run=subprocess.run([sys.executable,str(ROOT/'tools/test_orbtrace_board.py'),
            '--target-elf','unused','--bit','unused','--elf','unused','--output','unused',
            '--ddr-physical','--hclk-div','2'],capture_output=True,text=True)
        self.assertEqual(run.returncode,2)
        self.assertIn('preserves target clock',run.stderr)


if __name__=='__main__':unittest.main()
