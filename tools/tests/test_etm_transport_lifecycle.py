from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import struct

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
import zynq_la


class StartLifecycleTests(unittest.TestCase):
    def test_send_publishes_arm_before_recv_waits_for_end(self):
        session=SimpleNamespace(configure=Mock(),start=Mock(),wait=Mock(return_value=True),error=None)
        socket=zynq_la._Sock(SimpleNamespace(config={'traceid':2},traceid=2,seconds=.1))
        with patch.object(zynq_la,'session',return_value=session):
            socket.sendall(b'start')
            session.start.assert_called_once();session.wait.assert_not_called()
            socket.settimeout(10)
            self.assertEqual(socket.recv(4096),b'ACK')
            session.wait.assert_called_once_with(10)

    def test_receive_error_is_not_an_ack_or_replayed_start(self):
        session=SimpleNamespace(configure=Mock(),start=Mock(),wait=Mock(return_value=True),error='receiver lost')
        socket=zynq_la._Sock(SimpleNamespace(config={},traceid=2,seconds=.1))
        with patch.object(zynq_la,'session',return_value=session):
            socket.sendall(b'start')
            with self.assertRaises(zynq_la.CaptureError):socket.recv(4096)
            session.start.assert_called_once()

    def test_missing_diagnostics_are_unknown_not_zero_error(self):
        session=zynq_la.Session();session.dev=Mock()
        self.assertFalse(session.diagnostics()['implemented'])
        session.dev.ctrl_transfer.assert_not_called()
        session.diagnostics_supported=True
        words=[0x45544431,11,1,0,8,65536,12,0,0,99,0,0,100000,0,120000000,65536]
        session.dev.ctrl_transfer.return_value=struct.pack('<16I',*words)
        result=session.diagnostics()
        self.assertEqual(result['frameDrops'],12)
        self.assertIsNone(result['parserErrors']);self.assertIsNone(result['syncAcquisitions'])
        self.assertEqual(result['recordHighwater'],65536)
        self.assertFalse(result['receiverEnabled'])

    def test_reference_capability_and_diagnostics_signature_are_checked(self):
        session=zynq_la.Session();session.dev=Mock()
        session.dev.ctrl_transfer.return_value=struct.pack('<4I',200000000,1,2,0x101)
        self.assertEqual(session._reference_clock(),200000000)
        self.assertTrue(session.diagnostics_supported)
        session.dev.ctrl_transfer.return_value=b'\0'*64
        with self.assertRaises(zynq_la.CaptureError):session.diagnostics()


if __name__=='__main__':unittest.main()
