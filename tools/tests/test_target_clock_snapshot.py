from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from target_snapshot import same_clock_configuration


class ClockConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.before=dict(cpuid='0x411fc271',registers={'0x58024400':'0x33034025','0x58024430':'0xb010e5f'})

    def test_read_only_domain_ready_transition_keeps_raw_snapshots(self):
        after=deepcopy(self.before);after['registers']['0x58024400']='0x3303c025'
        self.assertTrue(same_clock_configuration(self.before,after))
        self.assertEqual(after['registers']['0x58024400'],'0x3303c025')
        self.assertEqual(self.before['registers']['0x58024400'],'0x33034025')

    def test_oscillator_pll_and_divisor_changes_remain_failures(self):
        for address,bit in [('0x58024400',12),('0x58024400',17),('0x58024400',24),('0x58024400',25),('0x58024430',0)]:
            after=deepcopy(self.before);after['registers'][address]=hex(int(after['registers'][address],0)^(1<<bit))
            self.assertFalse(same_clock_configuration(self.before,after),(address,bit))


if __name__=='__main__':unittest.main()
