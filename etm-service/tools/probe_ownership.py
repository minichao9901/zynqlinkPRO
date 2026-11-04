"""Cooperative process ownership shared by the service and native CLI tools.

An OS file lock, not a PID/stale-file heuristic, is authoritative. Multiple
USB/HID handles in one process share it. Process death releases the OS lock.
"""
import os
from pathlib import Path
import tempfile
import threading

_mutex=threading.RLock()
_stream=None
_references=0
_active_path=None


class Ownership:
    def __init__(self,path=None):
        base=Path(os.environ['LOCALAPPDATA']) if os.name=='nt' else Path.home()/'.cache'
        self.path=(Path(path) if path is not None else base/'ZynqLinkPro'/'probe-control-v1.lock').resolve()
        self.held=False
        self.acquire()

    def acquire(self):
        global _stream,_references,_active_path
        with _mutex:
            if self.held:return
            if _stream is None:
                # Frozen launchers deliberately replace TEMP per runtime;
                # ownership must stay in a common user directory instead.
                path=self.path
                path.parent.mkdir(parents=True,exist_ok=True)
                stream=os.fdopen(os.open(path,os.O_RDWR|os.O_CREAT,0o600),'r+b')
                try:
                    stream.seek(0,2)
                    if not stream.tell():stream.write(b'\0');stream.flush()
                    stream.seek(0)
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    stream.seek(1);stream.write(str(os.getpid()).encode('ascii'));stream.truncate();stream.flush()
                except OSError as error:
                    stream.close()
                    raise RuntimeError('另一进程仍持有Zynq探针；请先停止并断开原工作台/CLI') from error
                _stream=stream;_active_path=self.path
            elif _active_path!=self.path:
                raise RuntimeError('同一进程不能混用不同探针锁路径')
            _references+=1;self.held=True

    def close(self):
        global _stream,_references
        with _mutex:
            if not self.held:return
            self.held=False;_references-=1
            if not _references:
                _stream.close();_stream=None


def bind_usb(device,lease):
    """Retain public PyUSB dispose/reopen semantics while owning its handle."""
    context=device._ctx
    original_open,original_dispose=context.managed_open,context.dispose
    def managed_open():
        lease.acquire()
        try:return original_open()
        except BaseException:
            lease.close();raise
    def dispose(*args,**kwargs):
        result=original_dispose(*args,**kwargs)
        if kwargs.get('close_handle',args[1] if len(args)>1 else True):lease.close()
        return result
    context.managed_open=managed_open
    context.dispose=dispose
    return device
