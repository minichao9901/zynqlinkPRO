import queue
import threading
import sys
import time
import unittest
from pathlib import Path
import usb.core

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from native_hss import HssReceiver

class Device:
    def __init__(self):self.input=queue.Queue()
    def read(self,endpoint,length,timeout):
        try:return self.input.get(timeout=timeout/1000)
        except queue.Empty:raise usb.core.USBTimeoutError('quiet')

class HssReceiverTests(unittest.TestCase):
    def test_order_partial_batches_and_fresh_quiet_completion(self):
        device=Device();receiver=HssReceiver(device);self.addCleanup(receiver.close)
        payload=bytes(range(256))*4
        device.input.put(payload[:333]);device.input.put(payload[333:])
        raw=bytearray()
        while len(raw)<len(payload):raw.extend(receiver.read(512))
        self.assertEqual(raw,payload)
        self.assertEqual(receiver.read(512),b'')
        self.assertEqual((receiver.received,receiver.returned,receiver.queued),(1024,1024,0))

    def test_empty_queue_with_pending_usb_data_is_not_an_eof(self):
        release=threading.Event()
        class Pending:
            def read(self,*args,**kwargs):
                release.wait();raise usb.core.USBTimeoutError('quiet')
        receiver=HssReceiver(Pending());result=[]
        thread=threading.Thread(target=lambda:result.append(receiver.read(512)));thread.start()
        time.sleep(.02);self.assertTrue(thread.is_alive())
        release.set();thread.join(1);receiver.close()
        self.assertEqual(result,[b''])

    def test_overflow_is_explicit_and_never_a_truncated_success(self):
        device=Device();receiver=HssReceiver(device,capacity=512);self.addCleanup(receiver.close)
        device.input.put(b'a'*1024)
        with self.assertRaisesRegex(RuntimeError,'队列溢出'):receiver.read(65536)

    def test_closed_receiver_cannot_be_reused(self):
        receiver=HssReceiver(Device());receiver.close()
        with self.assertRaisesRegex(RuntimeError,'已关闭'):receiver.read(512)

if __name__=='__main__':unittest.main()
