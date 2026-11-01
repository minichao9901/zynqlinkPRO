import unittest
from tools.probe_clock_fixture import plan


class ClockPlanning(unittest.TestCase):
    def test_preserves_one_mhz_at_higher_fclk(self):
        old=1|(1<<8)|(15<<20) # 1.8GHz /15 =120MHz
        cfg=(11<<13)|(3<<28) # half-period60
        p=plan(old,54<<12,cfg,150000000)
        self.assertEqual(p['FCLK_Hz'],149999998)
        self.assertEqual(p['halfPeriod'],75)
        self.assertLess(abs(p['linkHz']-p['oldLinkHz']),0.01)
        self.assertEqual(p['cfg'] & ~0xf001e000,cfg & ~0xf001e000)

    def test_rejects_frequency_change_at_sixty_mhz(self):
        with self.assertRaisesRegex(ValueError,'preserve'):
            plan(1|(1<<8)|(15<<20),54<<12,0,150000000)

    def test_rejects_short_pulse_or_wrong_pll(self):
        for control,pll,cfg in [(1|(1<<8)|(15<<20),54<<12,1<<19),
                                 (0x11|(1<<8)|(15<<20),54<<12,0),
                                 (1|(1<<8)|(15<<20),(54<<12)|16,0)]:
            with self.assertRaises(ValueError):plan(control,pll,cfg,150000000)


if __name__=='__main__':unittest.main()
