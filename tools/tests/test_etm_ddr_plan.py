import unittest
from tools.plan_etm_ddr import plan


class DdrPlanTests(unittest.TestCase):
    def test_compact_four_bit_ddr_200mhz_two_seconds_has_400mb_payload(self):
        p=plan()
        self.assertEqual(p['payloadBytes'],400_000_000)
        self.assertFalse(p['fitsCapacity'])
        self.assertEqual(p['candidateCapacityBytes'],104857600)
        self.assertEqual(p['candidateBase'],0x39c00000)
        self.assertTrue(p['staticOverlaps'],'old Golden diagnostic reservation must move before using tail')
        self.assertFalse(p['safeForDeployment']);self.assertFalse(p['frequencyIsCapabilityClaim'])

    def test_sixteen_bit_records_do_not_fit_fixed_100mib_buffer_at_peak(self):
        p=plan(format='record16')
        self.assertEqual(p['payloadBytes'],800_000_000)
        self.assertFalse(p['fitsCapacity'])

    def test_existing_ddr_data_and_trace_reservations_are_not_reported_as_free(self):
        self.assertTrue(plan(base=0x00100000,capacity=0x01000000)['staticOverlaps'])
        self.assertTrue(plan(base=0x3f000000,capacity=0x00100000)['staticOverlaps'])
        self.assertTrue(plan(base=0x39000000,capacity=0x00100000)['staticOverlaps'])

    def test_candidates_outside_map_or_unaligned_fail_before_any_deployment(self):
        for arguments in ({'base':0},{'base':0x10000001},{'capacity':0x50000000},{'trace_hz':0}):
            with self.assertRaises(ValueError):plan(**arguments)


if __name__=='__main__':unittest.main()
