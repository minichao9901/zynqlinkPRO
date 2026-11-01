from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_etm_lane_delay import preflight


class LanePackageTests(unittest.TestCase):
    def test_only_completed_fresh_timing_closed_products_can_be_packaged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job=root/'job.json';log=root/'vivado.log';clock=root/'verified_clock.json';bit=root/'system_wrapper_verified.bit'
            now=datetime.now(timezone.utc).timestamp()
            job.write_text(json.dumps(dict(rawMode=4,etmDdr=1,laneDelay=1,implementFclkHz=120000000,startedUtc=datetime.fromtimestamp(now-1,timezone.utc).isoformat())))
            bit.write_bytes(b'offline identity fixture');clock.write_text(json.dumps(dict(FCLK_max_Hz=120000000,setup_slack_ns=.1,hold_slack_ns=.01)))
            log.write_text('VERIFIED_BITSTREAM_READY\n')
            with self.assertRaisesRegex(ValueError,'proof'):preflight(job,log,root)
            log.write_text('VERIFIED_BITSTREAM_READY\nORBTRACE_LANE_DELAY_VERIFIED count=5 VAR_LOAD=1 activeOutputs=5\nORBTRACE_OVERSAMPLE_VERIFIED META=5 SYNC=5\n')
            self.assertEqual(preflight(job,log,root)[1]['FCLK_max_Hz'],120000000)
            os.utime(bit,(now-100,now-100))
            with self.assertRaisesRegex(ValueError,'predates'):preflight(job,log,root)
            os.utime(bit,(now,now));clock.write_text(json.dumps(dict(FCLK_max_Hz=100000000,setup_slack_ns=.1,hold_slack_ns=.01)))
            with self.assertRaisesRegex(ValueError,'FCLK120'):preflight(job,log,root)


if __name__=='__main__':unittest.main()
