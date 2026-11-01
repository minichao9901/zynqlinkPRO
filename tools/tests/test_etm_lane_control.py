from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from etm_lane_delay import payload,decode,LaneDelay,SIGNATURE


class LaneDelayTests(unittest.TestCase):
    def test_five_lanes_pack_and_roundtrip_without_reserved_bits(self):
        taps=[0,3,7,16,31];value=payload(True,taps)
        row=decode([SIGNATURE,value,13,5,0,0])
        self.assertEqual(row['taps'],taps);self.assertTrue(row['enabled']);self.assertTrue(row['loaded'])
        self.assertEqual(value>>26,0)

    def test_missing_capability_and_invalid_values_fail_before_io(self):
        for enabled,taps in [(1,[0]*5),(True,[0]*4),(False,[0,0,0,0,32]),(False,[0,0,0,0,True]),(False,[1,0,0,0,0])]:
            with self.assertRaises(ValueError):payload(enabled,taps)
        for words in [[0]*6,[SIGNATURE,0,64,0,0,0],[SIGNATURE,1<<26,0,0,0,0]]:
            with self.assertRaises(ValueError):decode(words)

    def test_single_write_acknowledgement_and_no_replay_on_failure(self):
        class Memory:
            calls=0
            def run(self,body):
                self.calls+=1
                self.body=body
                self_outer.assertEqual(body.count('physwr '),1)
                return f'ELD_BEFORE {SIGNATURE} 0 4 1 0 0\nELD_AFTER {SIGNATURE} {payload(True,[0]*5)} 13 2 0 0\n'
        self_outer=self;memory=Memory();r=LaneDelay(memory).configure(True,[0]*5)
        self.assertTrue(r['after']['loaded']);self.assertEqual(memory.calls,1)
        memory.run=lambda body:(_ for _ in ()).throw(RuntimeError('CNTVALUEOUT mismatch'))
        with self.assertRaisesRegex(RuntimeError,'CNTVALUEOUT'):LaneDelay(memory).configure(False,[0]*5)


if __name__=='__main__':unittest.main()
