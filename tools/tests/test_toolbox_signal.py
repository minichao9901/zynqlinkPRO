import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trace_signal_analysis import unpack, filter_samples, physical


class SignalAnalysisTests(unittest.TestCase):
    def test_packing_rejects_transport_tag_and_preserves_all_five_lines(self):
        self.assertEqual(unpack(bytes.fromhex('4304')).tolist(),[1,2,3])
        with self.assertRaises(ValueError):unpack(b'\x00\x80')
        with self.assertRaises(ValueError):unpack(b'\x00')

    def test_filters_reject_single_tick_glitch_without_anticipating_an_edge(self):
        source=np.array([0,0,31,0,0,31,31,31],dtype=np.uint8)
        for method in ('majority3','stable2'):
            output=filter_samples(source,method)
            self.assertEqual(output[:6].tolist(),[0]*6)
            self.assertEqual(output[6:].tolist(),[31,31])
        self.assertEqual(filter_samples(source,'none').tolist(),source.tolist())

    def test_clock_uses_total_cycles_instead_of_quantized_median_period(self):
        # Alternating 5/6 sample periods: a median rounded to either one gives
        # a biased clock estimate; accumulated rising-edge intervals do not.
        source=np.zeros(58,dtype=np.uint8)
        for at in (1,6,12,17,23,28,34,39,45,50,56):source[at:at+2]=16
        result,_=physical(source,200_000_000)
        self.assertAlmostEqual(result['measuredTraceclkHz'],200_000_000*10/55)


if __name__=='__main__':unittest.main()
