"""Continuous bounded HSS bulk reception with an explicit USB quiet barrier."""
from collections import deque
import threading
import time
import usb.core


class HssOverflow(RuntimeError):
    pass


class HssReceiver:
    # Leave headroom for HTTP and rendering pauses during long eight-channel
    # captures, while keeping a fixed per-device allocation limit.
    def __init__(self,device,capacity=16*1024*1024):
        self.device=device;self.capacity=capacity;self.condition=threading.Condition()
        self.chunks=deque();self.queued=0;self.received=0;self.returned=0;self.high_water=0
        self.quiet_epoch=0;self.error=None;self.overflow=False;self.closed=False;self.quit=threading.Event()
        self.thread=threading.Thread(target=self._receive,name='native-HSS-reader',daemon=True)
        self.thread.start()

    def _receive(self):
        try:
            while not self.quit.is_set():
                try:data=bytes(self.device.read(0x87,65536,timeout=20))
                except usb.core.USBTimeoutError:data=b''
                if not data:
                    with self.condition:self.quiet_epoch+=1;self.condition.notify_all()
                    self.quit.wait(.001);continue
                with self.condition:
                    self.received+=len(data)
                    if self.overflow:
                        continue
                    if self.queued+len(data)>self.capacity:
                        self.overflow=True
                        self.chunks.clear()
                        self.queued=0
                        # The capture is failed. Keep the USB consumer alive
                        # until the owner can stop the producer and drain EP87.
                        self.condition.notify_all();continue
                    self.chunks.append(data);self.queued+=len(data)
                    self.high_water=max(self.high_water,self.queued);self.condition.notify_all()
        except Exception as error:
            if not self.quit.is_set():
                with self.condition:self.error=str(error);self.condition.notify_all()

    def read(self,limit,timeout=2,*,discard=False):
        # An empty queue alone does NOT prove EOF: an in-flight USB read may
        # still contain the producer's last packets. Require a fresh empty USB
        # completion after this request. STOP callers can then confirm the tail.
        end=time.monotonic()+timeout
        with self.condition:
            quiet_before=self.quiet_epoch
            if discard and not self.overflow:
                raise RuntimeError('HSS 队列未报告溢出，拒绝丢弃排空')
            while (not self.queued and not self.error and not self.closed and self.quiet_epoch==quiet_before
                   and (discard or not self.overflow)):
                left=end-time.monotonic()
                if left<=0:raise RuntimeError('本机HSS读取尚未确认USB静默，拒绝宣称尾部已排空')
                self.condition.wait(left)
            if self.closed:raise RuntimeError('本机HSS读取会话已关闭')
            if self.error:raise RuntimeError(self.error)
            if discard:
                return b''
            if self.overflow:
                raise HssOverflow('本机HSS接收队列溢出，数据不完整；请停止后重新连接')
            result=[];size=0
            while self.chunks and size<limit:
                data=self.chunks.popleft();take=min(len(data),limit-size)
                result.append(data[:take]);size+=take;self.queued-=take
                if take<len(data):self.chunks.appendleft(data[take:])
            self.returned+=size
            return b''.join(result)

    def close(self):
        self.quit.set();self.thread.join(1)
        if self.thread.is_alive():raise RuntimeError('本机HSS旧读取尚未退出，拒绝释放USB')
        with self.condition:self.closed=True;self.condition.notify_all()

    def queue_metrics(self):
        with self.condition:
            return {'highWaterBytes':self.high_water,'capacityBytes':self.capacity}
