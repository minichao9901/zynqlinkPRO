import unittest
from unittest.mock import Mock,patch
from tools.dap_pipeline_bench import setup


class ExactClockRequest(unittest.TestCase):
    def test_non_whole_khz_is_sent_exactly(self):
        calls=[]
        def command(out,inp,data):
            calls.append(data)
            if data[0]==2:return b'\x02\x01'
            if data==[5,0,1,2]:return bytes.fromhex('0501017714a01b')
            return bytes([data[0],0])
        with patch('tools.dap_pipeline_bench.drain'),patch('tools.dap_pipeline_bench.cmd',side_effect=command):
            setup(Mock(),Mock(),66666,speed_hz=66666666)
        clock=next(row for row in calls if row[0]==0x11)
        self.assertEqual(int.from_bytes(bytes(clock[1:]),'little'),66666666)

    def test_rejected_clock_never_continues_at_previous_rate(self):
        calls=[]
        def command(out,inp,data):
            calls.append(data)
            return b'\x02\x01' if data[0]==2 else b'\x11\xff'
        with patch('tools.dap_pipeline_bench.drain'),patch('tools.dap_pipeline_bench.cmd',side_effect=command):
            with self.assertRaisesRegex(RuntimeError,'Clock rejected'):
                setup(Mock(),Mock(),66667)
        self.assertEqual([r[0] for r in calls],[2,0x11])


if __name__=='__main__':unittest.main()
