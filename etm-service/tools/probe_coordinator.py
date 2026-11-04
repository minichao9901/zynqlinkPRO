"""One service control queue; data receivers deliberately bypass this queue.

Leases never expire into permission to touch hardware. Failed cleanup retains
the lease until its owner explicitly recovers it. Cancellation never replays an
operation and a running transport must acknowledge cancellation at a boundary.
"""
from collections import deque
from contextlib import contextmanager
import secrets
import threading
import time


class ProbeCancelled(RuntimeError):
    pass


class ProbeCoordinator:
    def __init__(self, max_pending=128):
        self.condition = threading.Condition(threading.RLock())
        self.pending = deque()
        self.current = None
        self.leases = {}
        self.max_pending = max_pending
        self.completed = self.failed = self.cancelled = 0

    def snapshot(self):
        with self.condition:
            def view(t):
                return {k: t[k] for k in ('id', 'owner', 'operation', 'phase')}
            return dict(protocol='probe-control/1', current=view(self.current) if self.current else None,
                        pending=[view(t) for t in self.pending],
                        resources={k: dict(v) for k, v in self.leases.items()},
                        completed=self.completed, failed=self.failed, cancelled=self.cancelled)

    def acquire(self, resource, owner):
        with self.condition:
            old = self.leases.get(resource)
            if old and old['owner'] != owner:
                raise ValueError(f'{resource}仍由另一会话占用')
            if old and old.get('error'):
                raise ValueError(f'{resource}清理未确认，需要原会话显式恢复')
            if resource == 'capture' and any(k != 'capture' for k in self.leases):
                raise ValueError('请先停止并释放探针USB/HID，再开始ETM采集')
            capture=self.leases.get('capture')
            if resource != 'capture' and capture and not (resource=='usb' and
                    capture.get('restoreOwner')==owner and capture.get('restoring') and not capture.get('error')):
                raise ValueError('ETM采集或恢复仍持有探针')
            if old:
                return old['epoch']
            epoch = secrets.token_hex(16)
            self.leases[resource] = dict(owner=owner, epoch=epoch, error=None)
            return epoch

    def begin_capture(self,record,restore_owner=None):
        with self.condition:
            self.acquire('capture',record)
            self.leases['capture'].update(restoreOwner=restore_owner,restoring=False)

    def finish_capture(self,record,error=None):
        with self.condition:
            lease=self.leases.get('capture')
            if not lease or lease['owner']!=record:return False
            if error:lease['error']=str(error)
            elif lease.get('restoreOwner'):lease['restoring']=True
            else:del self.leases['capture']
            self.condition.notify_all()
            return 'capture' in self.leases

    def complete_capture(self,record,owner):
        with self.condition:
            lease=self.leases.get('capture')
            if not lease:return
            if lease['owner']!=record or lease.get('restoreOwner')!=owner or not lease.get('restoring') or lease.get('error'):
                raise ValueError('采集恢复身份或硬件清理状态不匹配')
            del self.leases['capture'];self.condition.notify_all()

    def wait_for_restore(self,owner,check):
        with self.condition:
            while True:
                lease=self.leases.get('capture')
                if not lease or lease.get('restoreOwner')!=owner:return
                if lease.get('error'):raise ValueError('采集硬件清理未确认：'+lease['error'])
                if lease.get('restoring'):return
                check();self.condition.wait(.01)

    def release(self, resource, owner, error=None):
        with self.condition:
            lease = self.leases.get(resource)
            if not lease or lease['owner'] != owner:
                return
            if error:
                lease['error'] = str(error)
            else:
                del self.leases[resource]
            self.condition.notify_all()

    def cancel(self, owner):
        with self.condition:
            count = 0
            for ticket in list(self.pending) + ([self.current] if self.current else []):
                if ticket['owner'] == owner:
                    ticket['cancel'].set()
                    count += 1
            self.condition.notify_all()
            return dict(requested=count, activeMustDrain=bool(self.current and self.current['owner'] == owner))

    @contextmanager
    def operation(self, owner, operation, timeout=10):
        ticket = dict(id=secrets.token_hex(8), owner=owner, operation=operation,
                      phase='queued', cancel=threading.Event())
        until = time.monotonic() + timeout
        def check():
            if ticket['cancel'].is_set():
                raise ProbeCancelled('操作已取消；已执行的写入不会重放或自动撤销')
            if time.monotonic() >= until:
                raise TimeoutError('探针操作预算已耗尽；已执行的写入不会重放')
        with self.condition:
            if len(self.pending) >= self.max_pending:
                raise ValueError('探针控制队列已满')
            self.pending.append(ticket)
            try:
                while self.current is not None or self.pending[0] is not ticket:
                    check()
                    self.condition.wait(min(.05, max(0, until-time.monotonic())))
                check()
                self.pending.popleft()
                self.current = ticket
                ticket['phase'] = 'running'
            except BaseException:
                self.pending.remove(ticket)
                self.condition.notify_all()
                raise
        try:
            yield check
        except ProbeCancelled:
            with self.condition: self.cancelled += 1
            raise
        except BaseException:
            with self.condition: self.failed += 1
            raise
        else:
            with self.condition: self.completed += 1
        finally:
            with self.condition:
                self.current = None
                self.condition.notify_all()
