import unittest
import hashlib,json,sys,tempfile,types
from pathlib import Path
from unittest.mock import Mock,patch
from tools.probe_clock_fixture import Fixture,plan


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

    def test_real_nonshort_control_profiles_preserve_frequency(self):
        for old_div,requested in ((26,138461539),(24,150000000)):
            p=plan(1|(1<<8)|(old_div<<20),54<<12,1<<17,requested)
            self.assertEqual(p['halfPeriod'],2)
            self.assertLess(abs(p['linkHz']-p['oldLinkHz']),.51)

    def test_rejects_short_pulse_or_wrong_pll(self):
        for control,pll,cfg in [(1|(1<<8)|(15<<20),54<<12,1<<19),
                                 (0x11|(1<<8)|(15<<20),54<<12,0),
                                 (1|(1<<8)|(15<<20),(54<<12)|16,0)]:
            with self.assertRaises(ValueError):plan(control,pll,cfg,150000000)

    def test_untrusted_or_excessive_profile_never_opens_hardware(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(dir=root/'build') as temp:
            pair=Path(temp)
            (pair/'probe.bit').write_bytes(b'fixture-test-bit')
            (pair/'application.elf').write_bytes(b'fixture-test-elf')
            (pair/'verified_clock.json').write_text(json.dumps(dict(FCLK_max_Hz=150000000,setup_slack_ns=.1,hold_slack_ns=.1)))
            files={n:hashlib.sha256((pair/n).read_bytes()).hexdigest() for n in ('probe.bit','application.elf','verified_clock.json')}
            (pair/'manifest.json').write_text(json.dumps(dict(files=files)))
            session=Mock(side_effect=AssertionError('Hardware must remain unopened'))
            with patch.dict(sys.modules,{'probe_flash':types.SimpleNamespace(Session=session)}):
                with self.assertRaisesRegex(ValueError,'exceeds'):
                    Fixture(pair/'probe.bit',pair/'application.elf',163636364,pair/'excess')
                (pair/'verified_clock.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'hash mismatch'):
                    Fixture(pair/'probe.bit',pair/'application.elf',150000000,pair/'tampered')
            session.assert_not_called()


if __name__=='__main__':unittest.main()
