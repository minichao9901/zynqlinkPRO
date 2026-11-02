import sys,unittest,threading,queue,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'etm-service/tools'))
from native_serial import SerialReceiver

class Port:
    def __init__(self):self.input=queue.Queue();self.calls=[]
    def read(self,n):
        self.calls.append(n)
        try:return self.input.get(timeout=.02)
        except queue.Empty:return b''
    def cancel_read(self):self.input.put(b'')

def until(check):
    end=time.monotonic()+2
    while not check():
        if time.monotonic()>=end:raise AssertionError('Receiver did not reach test barrier')
        time.sleep(.001)

class ReceiverTests(unittest.TestCase):
    def test_com_is_drained_before_any_http_consumer_and_bytes_stay_ordered(self):
        port=Port();receiver=SerialReceiver(port)
        try:
            blocks=[bytes(range(256))*16,bytes(range(255,-1,-1))*16,b'tail']
            for b in blocks:port.input.put(b)
            until(lambda:receiver.snapshot()['receivedBytes']==sum(map(len,blocks)))
            self.assertEqual(receiver.snapshot()['returnedBytes'],0)
            self.assertEqual(receiver.read(limit=4100),b''.join(blocks)[:4100])
            self.assertEqual(receiver.read(),b''.join(blocks)[4100:])
            self.assertTrue(all(n==65536 for n in port.calls))
        finally:receiver.close()

    def test_overflow_is_a_failed_capture_never_silent_oldest_data_eviction(self):
        port=Port();receiver=SerialReceiver(port,capacity=8)
        try:
            port.input.put(b'12345678');port.input.put(b'9')
            until(lambda:receiver.snapshot()['error']is not None)
            with self.assertRaisesRegex(RuntimeError,'数据不完整'):receiver.read()
            self.assertEqual(receiver.snapshot()['highWaterBytes'],8)
        finally:receiver.close()

    def test_close_retires_old_reader_before_the_same_port_can_be_reused(self):
        port=Port();old=SerialReceiver(port);old.close()
        self.assertFalse(old.thread.is_alive())
        new=SerialReceiver(port)
        try:
            port.input.put(b'new epoch')
            self.assertEqual(new.read(timeout=1),b'new epoch')
            self.assertEqual(old.read(timeout=0),b'')
        finally:new.close()

    def test_physical_read_error_is_propagated_to_the_http_consumer(self):
        class Failing(Port):
            def read(self,n):raise OSError('unplugged')
        receiver=SerialReceiver(Failing())
        try:
            with self.assertRaisesRegex(RuntimeError,'unplugged'):receiver.read(timeout=1)
        finally:receiver.close()

if __name__=='__main__':unittest.main()
