"""Continuous COM reception, independent of browser/HTTP scheduling."""
from collections import deque
import threading
import time

class SerialReceiver:
    def __init__(self,port,capacity=4*1024*1024):
        self.port=port;self.capacity=capacity;self.condition=threading.Condition()
        self.chunks=deque();self.queued=0;self.received=0;self.returned=0;self.high_water=0
        self.error=None;self.closed=False;self.quit=threading.Event()
        self.thread=threading.Thread(target=self._receive,name='native-COM-reader',daemon=True)
        self.thread.start()

    def _receive(self):
        try:
            while not self.quit.is_set():
                # A large overlapped read stays active independently of HTTP
                # round trips. Small read(1)/in_waiting polls can leave the
                # Windows CDC path unread while a response/JS task is pending.
                data=bytes(self.port.read(65536))
                if self.quit.is_set():break
                if not data:
                    self.quit.wait(.001);continue
                with self.condition:
                    self.received+=len(data)
                    if self.queued+len(data)>self.capacity:
                        self.error='本地串口接收队列溢出，数据不完整；请停止转发后重新连接'
                        self.condition.notify_all();break
                    self.chunks.append(data);self.queued+=len(data)
                    self.high_water=max(self.high_water,self.queued);self.condition.notify_all()
        except Exception as error:
            if not self.quit.is_set():
                with self.condition:self.error=str(error);self.condition.notify_all()

    def read(self,limit=262144,timeout=.025):
        end=time.monotonic()+timeout
        with self.condition:
            while not self.queued and not self.error and not self.closed:
                left=end-time.monotonic()
                if left<=0:break
                self.condition.wait(left)
            if self.error:raise RuntimeError(self.error)
            result=[];size=0
            while self.chunks and size<limit:
                data=self.chunks.popleft();take=min(len(data),limit-size)
                result.append(data[:take]);size+=take;self.queued-=take
                if take<len(data):self.chunks.appendleft(data[take:])
            self.returned+=size
            return b''.join(result)

    def snapshot(self):
        with self.condition:return dict(receivedBytes=self.received,returnedBytes=self.returned,
            queuedBytes=self.queued,highWaterBytes=self.high_water,capacityBytes=self.capacity,error=self.error)

    def close(self):
        self.quit.set()
        if self.thread.is_alive()and hasattr(self.port,'cancel_read'):self.port.cancel_read()
        self.thread.join(2)
        if self.thread.is_alive():raise RuntimeError('本地串口旧读取尚未退出，拒绝复用端口')
        with self.condition:self.closed=True;self.condition.notify_all()
