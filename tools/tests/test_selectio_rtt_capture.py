"""Check negotiated RTT chunk selection and STOP reporting at the capture entry."""
from contextlib import nullcontext, redirect_stdout
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import selectio_cli


class RttCaptureTests(unittest.TestCase):
    def test_capture_uses_and_checks_the_selected_chunk(self):
        cases = [(4096,None,1024,1024), (16384,None,2048,2048),
                 (16384,1024,1024,1024), (16384,2048,2048,1024)]
        for frame, requested, expected, applied in cases:
            with self.subTest(frame=frame,requested=requested,applied=applied), tempfile.TemporaryDirectory() as folder:
                args=SimpleNamespace(action="rtt",serial="test",transport="swd",clock=50000000,
                                     seconds=0.5,out=Path(folder)/"bytes.rtt",chunk=requested,
                                     address=0x20008000,size=48,channel=0)
                native=Mock(frame_size=frame)
                native.info.return_value={}
                native.control.side_effect=lambda ch,op,data=b"": (0,[0]*11+[applied])
                chunks=iter([b"data",b"tail",b""])
                native.exchange.side_effect=lambda ch,op,*data: next(chunks) if op==1 else b""
                output=io.StringIO()
                with patch.object(selectio_cli,"connection",return_value=nullcontext((SimpleNamespace(device=None),None))), \
                     patch.object(selectio_cli,"native_connection",return_value=nullcontext(native)), \
                     patch.object(selectio_cli,"setup"),patch.object(selectio_cli,"cmd"), \
                     patch.object(selectio_cli.time,"monotonic",side_effect=[0,0.1,0.6,0.6,0.7]),redirect_stdout(output):
                    if expected==applied:
                        selectio_cli.capture(args)
                        result=json.loads(output.getvalue())
                        self.assertEqual((result["bytes"],result["rtt_chunk_bytes"]),(8,expected))
                    else:
                        with self.assertRaisesRegex(RuntimeError,"chunk readback"):
                            selectio_cli.capture(args)
                native.control.assert_any_call(2,7,struct.pack("<IHBB",50000000,expected,0,1))
                native.exchange.assert_any_call(2,0,b"\x00")
                self.assertEqual(args.out.read_bytes(),b"datatail")
