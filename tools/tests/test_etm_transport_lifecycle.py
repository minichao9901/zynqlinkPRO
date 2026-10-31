from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

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


if __name__=='__main__':unittest.main()
