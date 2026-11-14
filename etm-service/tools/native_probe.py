"""Opt-in loopback USB/HID/serial transport for the real Web workbench drivers.

No target protocol is emulated here: bytes go to the connected ZynqDAP/COM
devices. Browser-side DAP, RTT and scope parsers remain the source of behavior.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
import threading
import time
from pathlib import Path
from flask import abort, jsonify, request
from native_serial import SerialReceiver
from native_hss import HssReceiver
from probe_coordinator import ProbeCoordinator
from probe_memory import transfer as memory_transfer
from probe_ownership import Ownership
from probe_hid_control import HidControl


def drain_dap_replies(device,quiet_ms=80,limit=32):
    """Require a bounded quiet interval before a different DAP client starts."""
    import usb.core
    stale=0
    for _ in range(limit):
        try:device.read(0x81,4096,timeout=quiet_ms)
        except usb.core.USBTimeoutError:return stale
        stale+=1
    raise ValueError('DAP队列未静默，拒绝把旧响应交给新会话')


def reset_dap_session(device):
    """One acknowledged DAP-only epoch boundary, without resetting USB/target.

    Native ownership is exclusive before this call. A quiet host read alone
    cannot prove the device TX descriptor and software queues have retired.
    Existing firmware EP0 0x5a rebuilds only EP1 IN / EP2 OUT and aborts DAP
    engines; it does not touch target Flash/RCC or the DDR trace endpoint.
    """
    def snapshot():
        data=bytes(device.ctrl_transfer(0xc0,0x5b,0x4441,0x5052,32,timeout=2000))
        if len(data)!=32:raise ValueError('DAP队列状态长度无效')
        return struct.unpack('<8I',data)
    before=snapshot()
    result=bytes(device.ctrl_transfer(0xc0,0x5a,0x4441,0x5052,4,timeout=2000))
    if result!=b'DAP\0':raise ValueError('DAP专用会话复位未确认；没有重放命令')
    device.clear_halt(0x81);device.clear_halt(2)
    after=snapshot()
    if after[3]==before[3] or any(after[:3]):raise ValueError('DAP会话epoch或空闲队列未确认')
    return dict(syncProtocol='zynq-dap-epoch/1',queueEpoch=after[3],queueState=list(after[:3]))


class NativeProbe:
    def __init__(self, backend, token_file):
        self.backend = backend
        self.token = Path(token_file).read_text(encoding='ascii').strip()
        self.usb = None
        self.usb_owner = None
        self.usb_epoch = None
        self.usb_tainted = None
        self.claimed = set()
        self.hid = None
        self.hid_owner = None
        self.hid_epoch = None
        self.hid_control = None
        self.ports = {}
        self.serial_receivers = {}
        self.port_epochs = {}
        self.usb_lock = threading.RLock()
        self.hid_lock = threading.RLock()
        self.port_lock = threading.RLock()
        self.hss_stopping = True
        self.hss_receiver = None
        self.delivery_lock = threading.Condition()
        self.delivery_seen = set()
        self.delivery_cache = {}
        self.delivery_replays = 0
        self.delivery_requests = 0
        self.delivery_sessions = {}
        self.coordinator = ProbeCoordinator()
        self.physical_owners = {}
        self.capture_owners = {}

    def begin_capture(self,record,restore_owner):
        self.coordinator.begin_capture(record,restore_owner)
        try:self.capture_owners[record]=Ownership()
        except BaseException:
            self.coordinator.release('capture',record);raise

    def finish_capture(self,record,error=None):
        if not self.coordinator.finish_capture(record,error):
            lease=self.capture_owners.pop(record,None)
            if lease:lease.close()

    def complete_capture(self,record,owner):
        self.coordinator.complete_capture(record,owner)
        lease=self.capture_owners.pop(record,None)
        if lease:lease.close()

    def deliver(self, delivery, body, execute):
        """An HTTP redelivery must never repeat a USB write/read/serial action."""
        versioned = re.fullmatch(r'v2:([0-9a-f]{32}):([1-9][0-9]{0,15})', delivery or '')
        if not versioned and not re.fullmatch(r'[0-9a-f]{32}', delivery or ''):
            raise ValueError('无效传输请求ID')
        signature = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with self.delivery_lock:
            entry = self.delivery_cache.get(delivery)
            if entry is not None:
                if entry['signature'] != signature:
                    raise ValueError('同一传输ID的内容不一致')
                while not entry['done']:
                    self.delivery_lock.wait(timeout=1)
                self.delivery_replays += 1
                return entry['result']
            if versioned:
                session, sequence = versioned[1], int(versioned[2])
                if sequence > 9007199254740991:
                    raise ValueError('传输序号超出范围')
                if session not in self.delivery_sessions:
                    if len(self.delivery_sessions) >= 4096:
                        raise ValueError('本地传输客户端数量过多；现有客户端仍可清理硬件')
                    self.delivery_sessions[session] = (0, 0)
                highest, bits = self.delivery_sessions[session]
                if sequence > highest:
                    shift = sequence - highest
                    bits = 1 if shift >= 4096 else ((bits << shift) | 1) & ((1 << 4096) - 1)
                    highest = sequence
                else:
                    offset = highest - sequence
                    if offset >= 4096 or bits & (1 << offset):
                        raise ValueError('传输结果已回收或序号过旧；拒绝重放硬件动作')
                    bits |= 1 << offset
                self.delivery_sessions[session] = (highest, bits)
            else:
                # Old clients retain fail-closed UUID tombstones. Updated
                # clients use bounded sequence windows, without a request cap.
                if delivery in self.delivery_seen:
                    raise ValueError('传输结果已回收；拒绝重放硬件动作')
                if len(self.delivery_seen) >= 100000:
                    raise ValueError('旧版本地传输会话已达100000请求；请升级页面')
                self.delivery_seen.add(delivery)
            self.delivery_requests += 1
            entry = dict(signature=signature, done=False, result=None)
            self.delivery_cache[delivery] = entry
        try:
            result = execute()
        except Exception as error:
            result = ({'ok': False, 'error': str(error), 'type': type(error).__name__}, 400)
        with self.delivery_lock:
            entry.update(done=True, result=result)
            # Pending replies stay pinned. Evicted v2 results remain marked
            # in a bounded bit window; older sequence numbers fail closed.
            for key in list(self.delivery_cache):
                if len(self.delivery_cache) <= 256:
                    break
                if key != delivery and self.delivery_cache[key]['done']:
                    del self.delivery_cache[key]
            self.delivery_lock.notify_all()
        return result

    def busy(self):
        b = self.backend
        with b.lock:
            return any(j.get('kind', 'capture') == 'capture' and
                       (j['state'] in b.ACTIVE or j.get('_laLease') or j.get('cleanupPending')) for j in b.jobs.values())

    @staticmethod
    def blob(value, limit=262144):
        data = base64.b64decode(value, validate=True)
        if len(data) > limit:
            raise ValueError('传输块过大')
        return data

    @staticmethod
    def encode(data):
        return base64.b64encode(bytes(data)).decode('ascii')

    def descriptor(self, device):
        config = device.get_active_configuration()
        interfaces = {}
        for interface in config:
            row = interfaces.setdefault(interface.bInterfaceNumber, {'interfaceNumber': interface.bInterfaceNumber,
                                                                     'claimed': interface.bInterfaceNumber in self.claimed,
                                                                     'alternates': []})
            alternate = {'alternateSetting': interface.bAlternateSetting, 'interfaceClass': interface.bInterfaceClass,
                         'interfaceSubclass': interface.bInterfaceSubClass, 'interfaceProtocol': interface.bInterfaceProtocol,
                         'endpoints': [{'endpointNumber': e.bEndpointAddress & 15,
                                        'direction': 'in' if e.bEndpointAddress & 128 else 'out',
                                        'type': {0: 'control', 1: 'isochronous', 2: 'bulk', 3: 'interrupt'}[e.bmAttributes & 3],
                                        'packetSize': e.wMaxPacketSize} for e in interface]}
            row['alternates'].append(alternate)
            if 'alternate' not in row:
                row['alternate'] = alternate
        return {'vendorId': device.idVendor, 'productId': device.idProduct, 'manufacturerName': device.manufacturer,
                'productName': device.product, 'serialNumber': device.serial_number,
                'configuration': {'configurationValue': config.bConfigurationValue, 'interfaces': list(interfaces.values())}}

    @staticmethod
    def find_usb():
        import libusb_package
        import usb.core
        devices = [d for d in usb.core.find(find_all=True, idVendor=0x0D28, idProduct=0x0204,
                                            backend=libusb_package.get_libusb1_backend())
                   if d.manufacturer == 'CherryUSB' and d.product == 'CMSIS-DAP']
        if len(devices) != 1:
            raise ValueError('本地探针服务需要唯一的 zynqlinkPRO 探针，当前数量：' + str(len(devices)))
        return devices[0]

    @staticmethod
    def find_hid():
        import hid
        return [d for d in hid.enumerate(0x0D28, 0x0204)
                if d['usage_page'] == 0xFF00 and d['manufacturer_string'] == 'CherryUSB'
                and d['product_string'] in ('zynqlinkPRO HID', 'CMSIS-DAP')]

    def _stop_hss_receiver(self):
        if self.hss_receiver is not None:
            self.hss_receiver.close()
            self.hss_receiver = None

    def session_call(self, action, value):
        if action == 'status':
            status=self.coordinator.snapshot()
            status['transport']=dict(usbOpen=self.usb is not None,usbError=self.usb_tainted,
                hidOpen=self.hid is not None,hidCorrelated=bool(self.hid_control and self.hid_control.correlated),
                hidStaleReplies=self.hid_control.stale if self.hid_control else 0)
            return status
        owner = value.get('owner', '')
        if not re.fullmatch(r'[0-9a-f]{32}', owner):
            raise ValueError('无效探针会话身份')
        if action == 'cancel':
            result=self.coordinator.cancel(owner)
            with self.backend.lock:
                captures=[jid for jid,j in self.backend.jobs.items() if j.get('restoreOwner')==owner and j['state'] in self.backend.ACTIVE]
            if len(captures)>1:raise ValueError('恢复会话对应多个活动采集，拒绝猜测停止对象')
            if captures:
                result['captureStop']=self.backend.stop_capture(captures[0]).get_json()
            return result
        raise ValueError('未知会话动作')

    def _controlled(self, kind, action, value, execute):
        owner = value.get('owner', 'inspect')
        with self.coordinator.operation(owner, kind+'/'+action) as check:
            if action == 'open':
                self.coordinator.wait_for_restore(owner,check)
                if self.busy():
                    raise ValueError('ETM采集或清理尚未结束')
                if getattr(self,kind) is not None and getattr(self,kind+'_owner') != owner:
                    raise ValueError('另一Web会话仍持有本地探针通路')
                self.coordinator.acquire(kind, owner)
                try:
                    if kind not in self.physical_owners:self.physical_owners[kind]=Ownership()
                except BaseException:
                    self.coordinator.release(kind,owner);raise
            try:
                result = execute(check)
            except BaseException as error:
                if action == 'open' and getattr(self, kind) is None:
                    self.coordinator.release(kind, owner)
                    lease=self.physical_owners.pop(kind,None)
                    if lease:lease.close()
                elif action in ('open', 'close', 'release'):
                    self.coordinator.release(kind, owner, error)
                raise
            if action == 'close' and not result.get('superseded'):
                self.coordinator.release(kind, owner)
                if getattr(self,kind) is None:
                    lease=self.physical_owners.pop(kind,None)
                    if lease:lease.close()
            return result

    def usb_call(self, action, value):
        # A continuous HSS reader is a data plane, not a control operation.
        if action == 'read' and value.get('endpoint') == 0x87:
            return self._usb_call(action, value)
        return self._controlled('usb', action, value, lambda check: self._usb_call(action, value, check))

    def _usb_call(self, action, value, check=lambda: None):
        import usb.core
        import usb.util
        with self.usb_lock:
            if action == 'list':
                if self.busy():
                    raise ValueError('ETM采集期间不枚举探针')
                if self.usb is not None:
                    return [self.descriptor(self.usb)]
                device = self.find_usb()
                try:
                    return [self.descriptor(device)]
                finally:
                    usb.util.dispose_resources(device)
            owner = value.get('owner', '')
            if not re.fullmatch(r'[0-9a-f]{32}', owner):
                raise ValueError('无效USB会话身份')
            if action == 'open':
                if self.busy():
                    raise ValueError('ETM采集或清理尚未结束')
                if self.usb is not None and owner != self.usb_owner:
                    raise ValueError('另一Web会话仍持有本地USB通路')
                if self.usb is not None:
                    # A page reload/reprogram can retain this owner's logical
                    # identity while invalidating its old native OS handle.
                    self._stop_hss_receiver()
                    for interface in list(self.claimed):
                        try: usb.util.release_interface(self.usb, interface)
                        except usb.core.USBError: pass
                    usb.util.dispose_resources(self.usb)
                    self.usb=None;self.claimed.clear()
                if self.usb is None:
                    self.usb = self.find_usb()
                    self.usb_owner = owner
                self.usb_epoch=secrets.token_hex(16)
                return {**self.descriptor(self.usb),'resourceEpoch':self.usb_epoch}
            if self.usb is None or owner != self.usb_owner:
                if action == 'close':
                    return {'closed': True}
                raise ValueError('USB会话已关闭或已更换')
            device = self.usb
            if value.get('resourceEpoch') is not None and value['resourceEpoch'] != self.usb_epoch:
                if action == 'close':return {'closed':True,'superseded':True}
                raise ValueError('USB通路已重新打开；拒绝旧会话操作')
            if action == 'close':
                self._stop_hss_receiver()
                for interface in list(self.claimed):
                    usb.util.release_interface(device, interface)
                    self.claimed.remove(interface)
                usb.util.dispose_resources(device)
                self.usb = self.usb_owner = None
                return {'closed': True}
            if self.busy():
                raise ValueError('ETM采集期间禁止竞争USB通路')
            if action == 'read-descriptor':
                descriptor, index, length = (value.get(key) for key in ('value', 'index', 'length'))
                if (type(descriptor) is not int or descriptor >> 8 not in (1, 2, 3) or
                        type(index) is not int or not 0 <= index <= 0xffff or
                        type(length) is not int or not 1 <= length <= 4096):
                    raise ValueError('只允许读取标准 USB 设备、配置或字符串描述符')
                return {'data': self.encode(device.ctrl_transfer(0x80, 6, descriptor, index, length, timeout=2000))}
            if action == 'configuration':
                if value.get('number') != 1:
                    raise ValueError('只支持配置1')
                if device.get_active_configuration().bConfigurationValue != 1:
                    self._stop_hss_receiver()
                    device.set_configuration(1)
                return self.descriptor(device)
            if action in ('claim', 'release'):
                if value.get('number') != 0:
                    raise ValueError('本地USB只允许厂商接口0')
                if action == 'claim' and 0 not in self.claimed:
                    usb.util.claim_interface(device, 0)
                    self.claimed.add(0)
                    try:
                        synchronized=reset_dap_session(device)
                    except BaseException:
                        usb.util.release_interface(device,0);self.claimed.remove(0)
                        raise
                    self.usb_tainted=None
                    return {'ok':True,**synchronized,'atomicDapExchange':1,'bulkArmMemory':1}
                elif action == 'release' and 0 in self.claimed:
                    self._stop_hss_receiver()
                    usb.util.release_interface(device, 0)
                    self.claimed.remove(0)
                return {'ok': True}
            if action == 'alternate':
                if value.get('number') != 0 or value.get('alternate') != 0:
                    raise ValueError('不支持此alternate')
                return {'ok': True}
            if action == 'reset':
                self._stop_hss_receiver()
                device.reset()
                return {'ok': True}
            ep = value.get('endpoint')
            if action == 'clear':
                if ep not in (2, 0x81, 0x82, 0x87):
                    raise ValueError('不支持此端点')
                if ep == 0x87:self._stop_hss_receiver()
                device.clear_halt(ep)
                return {'ok': True}
            if 0 not in self.claimed:
                raise ValueError('请先认领USB接口0')
            if action == 'recover':
                if self.hid is not None or self.hss_receiver is not None:
                    raise ValueError('请先停止数据流并关闭HID/HSS，再重建DAP会话')
                synchronized=reset_dap_session(device)
                self.usb_epoch=secrets.token_hex(16);self.usb_tainted=None
                return {**synchronized,'resourceEpoch':self.usb_epoch,'targetReconnectRequired':True}
            if self.usb_tainted and action in ('exchange','write','read','memory-read','memory-write'):
                raise ValueError('前次DAP事务未完整确认，请显式恢复或断开重连：'+self.usb_tainted)
            if action in ('memory-read', 'memory-write'):
                if value.get('transport') != 'swd':
                    raise ValueError('批量内存当前仅允许已连接的ARM SWD')
                wire_started=False
                def exchange(data):
                    nonlocal wire_started
                    wire_started=True
                    written=device.write(2,data,timeout=2000)
                    if written!=len(data):raise ValueError('DAP请求短写；未重放命令')
                    if len(data)%512==0:device.write(2,b'',timeout=2000)
                    return bytes(device.read(0x81,4096,timeout=2000))
                try:
                    result=memory_transfer(exchange,address=value.get('address'),length=value.get('length'),
                        data=self.blob(value.get('data','')) if action=='memory-write' else None,
                        ap=value.get('ap',0),csw=value.get('csw',0x23000052),check=check)
                except Exception as error:
                    # Validation errors have no effects; every other failure
                    # may have consumed a request or partially written RAM.
                    if wire_started:self.usb_tainted=str(error)
                    raise
                return {'bytesWritten':result} if action=='memory-write' else {'data':self.encode(result)}
            if action == 'exchange':
                # One HTTP round trip for a serialized DAP write+read. A
                # duplicate delivery ID is handled outside this lock and must
                # never execute the write a second time.
                data=self.blob(value.get('data',''),4096)
                length=value.get('length',512);budget=value.get('timeoutMs',2000)
                if not data or not isinstance(length,int) or not 1<=length<=4096 or not isinstance(budget,int) or not 1<=budget<=2000:
                    raise ValueError('无效DAP交换参数')
                until=time.monotonic()+budget/1000
                written=device.write(2,data,timeout=budget)
                if written!=len(data):raise ValueError('DAP请求短写；未重放命令')
                def remaining():
                    return max(1,int((until-time.monotonic())*1000))
                if len(data)%512==0:device.write(2,b'',timeout=remaining())
                try:reply=bytes(device.read(0x81,length,timeout=remaining()))
                except usb.core.USBTimeoutError:return {'data':'','timedOut':True,'bytesWritten':written}
                return {'data':self.encode(reply),'timedOut':False,'bytesWritten':written}
            if action == 'write':
                if ep != 2:
                    raise ValueError('仅允许DAP OUT端点2')
                data = self.blob(value.get('data', ''), 4096)
                return {'bytesWritten': device.write(2, data, timeout=2000)}
            if action == 'read':
                if ep not in (0x81, 0x87):
                    raise ValueError('仅允许DAP/HSS bulk IN')
                length = value.get('length', 4096)
                if not isinstance(length, int) or not 1 <= length <= 65536:
                    raise ValueError('无效读取长度')
                data = bytearray()
                timeout = 2000 if value.get('commandPending') else 25
                if ep == 0x81:
                    try:
                        data.extend(device.read(ep, length, timeout=timeout))
                    except usb.core.USBTimeoutError:
                        return {'data': '', 'timedOut': True}
                else:
                    read_length = length // 512 * 512
                    if read_length:
                        if self.hss_receiver is None:self.hss_receiver=HssReceiver(device)
                        data.extend(self.hss_receiver.read(read_length))
                return {'data': self.encode(data), 'timedOut': not data}
            raise ValueError('未知USB动作')

    def hid_call(self, action, value):
        return self._controlled('hid', action, value, lambda check: self._hid_call(action, value))

    def _hid_call(self, action, value):
        import hid
        with self.hid_lock:
            if self.busy():
                raise ValueError('ETM事务期间HID通路暂停')
            if action == 'list':
                return [{'vendorId': d['vendor_id'], 'productId': d['product_id'],
                         'serialNumber': d['serial_number'], 'productName': d['product_string'],
                         'collections': [{'usagePage': d['usage_page'], 'usage': d['usage']}]} for d in
                        self.find_hid()]
            owner = value.get('owner', '')
            if not re.fullmatch(r'[0-9a-f]{32}', owner):
                raise ValueError('无效HID会话')
            if action == 'open':
                if self.hid is not None and owner != self.hid_owner:
                    raise ValueError('另一Web会话仍持有HID')
                if self.hid is not None:
                    self.hid.close();self.hid=None
                if self.hid is None:
                    matches = self.find_hid()
                    if len(matches) != 1:
                        raise ValueError('需要唯一的 zynqlinkPRO HID 接口')
                    self.hid = hid.device()
                    self.hid.open_path(matches[0]['path'])
                    self.hid_owner = owner
                    for _ in range(32):
                        if not self.hid.read(64,1):break
                self.hid_epoch=secrets.token_hex(16)
                self.hid_control=HidControl(self.hid)
                correlated=self.hid_control.negotiate()
                return {'opened': True,'resourceEpoch':self.hid_epoch,'correlatedHid':correlated}
            if self.hid is None or owner != self.hid_owner:
                if action == 'close':
                    return {'closed': True}
                raise ValueError('HID会话已关闭')
            if value.get('resourceEpoch') is not None and value['resourceEpoch'] != self.hid_epoch:
                if action == 'close':return {'closed':True,'superseded':True}
                raise ValueError('HID通路已重新打开；拒绝旧会话操作')
            if action == 'close':
                self.hid.close()
                self.hid = self.hid_owner = None
                return {'closed': True}
            if action == 'report':
                data = self.blob(value.get('data', ''), 63)
                if value.get('reportId') != 1 or len(data) != 63:
                    raise ValueError('HID要求report 1 + 63-byte payload')
                reply=self.hid_control.exchange(data)
                return {'reportId':2,'data':self.encode(reply[1:]),'staleReplies':self.hid_control.stale}
            raise ValueError('未知HID动作')

    def serial_call(self, action, value):
        # Epoch validation and resource selection must be one operation.
        # An old HTTP read/close cannot consume or retire a reopened port.
        # Physical reception has its own thread and never needs this lock.
        with self.port_lock:
            return self._serial_call(action, value)

    def _serial_call(self, action, value):
        import serial
        import serial.tools.list_ports
        if action == 'list':
            return [{'path': p.device, 'productName': p.description,
                     'usbVendorId': p.vid, 'usbProductId': p.pid, 'serialNumber': p.serial_number}
                    for p in serial.tools.list_ports.comports()]
        owner, path = value.get('owner', ''), value.get('path', '')
        if not re.fullmatch(r'[0-9a-f]{32}', owner):
            raise ValueError('无效串口会话')
        key = (owner, path)
        if action == 'open':
            with self.port_lock:
                if key in self.ports:
                    self.serial_receivers[key].close()
                    self.ports.pop(key).close();self.serial_receivers.pop(key)
                if path not in {p.device for p in serial.tools.list_ports.comports()}:
                    raise ValueError('串口不存在')
                if any(p == path for _, p in self.ports):
                    raise ValueError('串口已被另一Web会话使用')
                o = value.get('options') or {}
                size = int(o.get('bufferSize', 4096))
                if not 1024 <= size <= 1048576:
                    raise ValueError('串口bufferSize须为1024..1048576')
                port = serial.Serial(path, baudrate=int(o.get('baudRate', 115200)),
                    bytesize=int(o.get('dataBits', 8)), stopbits=int(o.get('stopBits', 1)),
                    parity={'none': 'N', 'even': 'E', 'odd': 'O'}[o.get('parity', 'none')],
                    rtscts=o.get('flowControl') == 'hardware', timeout=.015, write_timeout=2)
                try:
                    if hasattr(port, 'set_buffer_size'):
                        port.set_buffer_size(rx_size=size, tx_size=size)
                except Exception:
                    port.close()
                    raise
                self.ports[key] = port
                self.port_epochs[key]=secrets.token_hex(16)
                self.serial_receivers[key]=SerialReceiver(port)
                return {'opened': True,'resourceEpoch':self.port_epochs[key]}
        port = self.ports.get(key)
        if port is None:
            if action == 'close':
                return {'closed': True}
            raise ValueError('串口未打开')
        if value.get('resourceEpoch') is not None and value['resourceEpoch'] != self.port_epochs.get(key):
            if action == 'close':return {'closed':True,'superseded':True}
            raise ValueError('串口已重新打开；拒绝旧会话操作')
        if action == 'read':
            data = self.serial_receivers[key].read()
            return {'data': self.encode(data)}
        if action == 'write':
            return {'bytesWritten': port.write(self.blob(value.get('data', '')))}
        if action == 'signals':
            o = value.get('signals') or {}
            if 'dataTerminalReady' in o:
                port.dtr = bool(o['dataTerminalReady'])
            if 'requestToSend' in o:
                port.rts = bool(o['requestToSend'])
            if 'break' in o:
                port.break_condition = bool(o['break'])
            return {'ok': True}
        if action == 'get-signals':
            return {'clearToSend': port.cts, 'dataSetReady': port.dsr,
                    'ringIndicator': port.ri, 'dataCarrierDetect': port.cd}
        if action == 'close':
            with self.port_lock:
                self.serial_receivers[key].close()
                port.close()
                self.ports.pop(key, None)
                self.serial_receivers.pop(key,None)
                self.port_epochs.pop(key,None)
            return {'closed': True}
        raise ValueError('未知串口动作')


def install(app, backend, token_file):
    proxy = NativeProbe(backend, token_file)
    backend.app.extensions['native_probe'] = proxy

    @app.post('/native-probe/<kind>/<action>')
    def dispatch(kind, action):
        if request.remote_addr not in ('127.0.0.1', '::1'):
            abort(403)
        if request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
            abort(403)
        if not hmac.compare_digest(request.headers.get('X-Trace-CLI', ''), proxy.token):
            abort(403)
        value = request.get_json()
        if not isinstance(value, dict) or (request.content_length or 0) > 400000:
            abort(400)
        def execute():
            handlers = {'usb': proxy.usb_call, 'hid': proxy.hid_call, 'serial': proxy.serial_call,
                        'session': proxy.session_call}
            if kind not in handlers:
                raise ValueError('未知本地探针通路')
            return ({'ok': True, 'value': handlers[kind](action, value)}, 200)
        try:
            if kind == 'meta' and action == 'status':
                with proxy.delivery_lock:
                    return jsonify(ok=True, value={'requests': proxy.delivery_requests,
                        'redeliveries': proxy.delivery_replays, 'cached': len(proxy.delivery_cache),
                        'sequenceClients': len(proxy.delivery_sessions), 'legacyRequests': len(proxy.delivery_seen),
                        'control':proxy.coordinator.snapshot()})
            delivery = request.headers.get('X-Trace-Delivery')
            if delivery:
                result, status = proxy.deliver(delivery, {'kind': kind, 'action': action, 'value': value}, execute)
                return jsonify(result), status
            result, status = execute()
            return jsonify(result), status
        except Exception as error:
            return jsonify(ok=False, error=str(error), type=type(error).__name__), 400

    return proxy
