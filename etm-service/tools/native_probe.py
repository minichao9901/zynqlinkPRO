"""Opt-in loopback USB/HID/serial transport for the real Web workbench drivers.

No target protocol is emulated here: bytes go to the connected ZynqDAP/COM
devices. Browser-side DAP, RTT and scope parsers remain the source of behavior.
"""
import base64
import hmac
import re
import threading
import time
from pathlib import Path
from flask import abort, jsonify, request


class NativeProbe:
    def __init__(self, backend, token_file):
        self.backend = backend
        self.token = Path(token_file).read_text(encoding='ascii').strip()
        self.usb = None
        self.usb_owner = None
        self.claimed = set()
        self.hid = None
        self.hid_owner = None
        self.ports = {}
        self.usb_lock = threading.RLock()
        self.hid_lock = threading.RLock()
        self.port_lock = threading.RLock()
        self.hss_stopping = True

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
        return {'vendorId': device.idVendor, 'productId': device.idProduct,
                'productName': device.product, 'serialNumber': device.serial_number,
                'configuration': {'configurationValue': config.bConfigurationValue, 'interfaces': list(interfaces.values())}}

    @staticmethod
    def find_usb():
        import libusb_package
        import usb.core
        devices = list(usb.core.find(find_all=True, idVendor=0x0D28, idProduct=0x0204,
                                    backend=libusb_package.get_libusb1_backend()))
        if len(devices) != 1:
            raise ValueError('本地探针服务要求唯一ZynqDAP；当前数量：' + str(len(devices)))
        return devices[0]

    def usb_call(self, action, value):
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
                if self.usb is None:
                    self.usb = self.find_usb()
                    self.usb_owner = owner
                return self.descriptor(self.usb)
            if self.usb is None or owner != self.usb_owner:
                if action == 'close':
                    return {'closed': True}
                raise ValueError('USB会话已关闭或已更换')
            device = self.usb
            if action == 'close':
                for interface in list(self.claimed):
                    usb.util.release_interface(device, interface)
                    self.claimed.remove(interface)
                usb.util.dispose_resources(device)
                self.usb = self.usb_owner = None
                return {'closed': True}
            if self.busy():
                raise ValueError('ETM采集期间禁止竞争USB通路')
            if action == 'configuration':
                if value.get('number') != 1:
                    raise ValueError('只支持配置1')
                if device.get_active_configuration().bConfigurationValue != 1:
                    device.set_configuration(1)
                return self.descriptor(device)
            if action in ('claim', 'release'):
                if value.get('number') != 0:
                    raise ValueError('本地USB只允许厂商接口0')
                if action == 'claim' and 0 not in self.claimed:
                    usb.util.claim_interface(device, 0)
                    self.claimed.add(0)
                    # Unlike browser USB, libusb provides a cancellable timeout.
                    # Drain the preceding owner's replies before Web resync sends
                    # its fixed eight Disconnects, otherwise a ninth old reply can
                    # masquerade as the next DAP_Info response.
                    stale = 0
                    for _ in range(32):
                        try:
                            device.read(0x81, 4096, timeout=10)
                            stale += 1
                        except usb.core.USBTimeoutError:
                            break
                    return {'ok': True, 'staleDapReplies': stale}
                elif action == 'release' and 0 in self.claimed:
                    usb.util.release_interface(device, 0)
                    self.claimed.remove(0)
                return {'ok': True}
            if action == 'alternate':
                if value.get('number') != 0 or value.get('alternate') != 0:
                    raise ValueError('不支持此alternate')
                return {'ok': True}
            if action == 'reset':
                device.reset()
                return {'ok': True}
            ep = value.get('endpoint')
            if action == 'clear':
                if ep not in (2, 0x81, 0x82, 0x87):
                    raise ValueError('不支持此端点')
                device.clear_halt(ep)
                return {'ok': True}
            if 0 not in self.claimed:
                raise ValueError('请先认领USB接口0')
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
                    # Read complete HSS packets so a partial large libusb
                    # timeout cannot silently discard already-received bytes.
                    deadline = time.monotonic() + .04
                    while len(data) + 512 <= length and time.monotonic() < deadline:
                        try:
                            chunk = bytes(device.read(ep, 512, timeout=10))
                        except usb.core.USBTimeoutError:
                            break
                        data.extend(chunk)
                        if len(chunk) < 512:
                            break
                return {'data': self.encode(data), 'timedOut': not data}
            raise ValueError('未知USB动作')

    def hid_call(self, action, value):
        import hid
        with self.hid_lock:
            if self.busy():
                raise ValueError('ETM事务期间HID通路暂停')
            if action == 'list':
                return [{'vendorId': d['vendor_id'], 'productId': d['product_id'],
                         'serialNumber': d['serial_number'], 'productName': d['product_string'],
                         'collections': [{'usagePage': d['usage_page'], 'usage': d['usage']}]} for d in
                        hid.enumerate(0x0D28, 0x0204) if d['usage_page'] == 0xFF00]
            owner = value.get('owner', '')
            if not re.fullmatch(r'[0-9a-f]{32}', owner):
                raise ValueError('无效HID会话')
            if action == 'open':
                if self.hid is not None and owner != self.hid_owner:
                    raise ValueError('另一Web会话仍持有HID')
                if self.hid is None:
                    matches = [d for d in hid.enumerate(0x0D28, 0x0204) if d['usage_page'] == 0xFF00]
                    if len(matches) != 1:
                        raise ValueError('需要唯一ZynqDAP HID')
                    self.hid = hid.device()
                    self.hid.open_path(matches[0]['path'])
                    self.hid_owner = owner
                return {'opened': True}
            if self.hid is None or owner != self.hid_owner:
                if action == 'close':
                    return {'closed': True}
                raise ValueError('HID会话已关闭')
            if action == 'close':
                self.hid.close()
                self.hid = self.hid_owner = None
                return {'closed': True}
            if action == 'report':
                data = self.blob(value.get('data', ''), 63)
                if value.get('reportId') != 1 or len(data) != 63:
                    raise ValueError('HID要求report 1 + 63-byte payload')
                self.hid.write(bytes([1]) + data)
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    reply = bytes(self.hid.read(64, 100))
                    if len(reply) == 64 and reply[0] == 2 and reply[2] == data[1]:
                        return {'reportId': 2, 'data': self.encode(reply[1:])}
                raise TimeoutError('本地HID响应超时；未重放命令')
            raise ValueError('未知HID动作')

    def serial_call(self, action, value):
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
                    return {'opened': True}
                if path not in {p.device for p in serial.tools.list_ports.comports()}:
                    raise ValueError('串口不存在')
                if any(p == path for _, p in self.ports):
                    raise ValueError('串口已被另一Web会话使用')
                o = value.get('options') or {}
                self.ports[key] = serial.Serial(path, baudrate=int(o.get('baudRate', 115200)),
                    bytesize=int(o.get('dataBits', 8)), stopbits=int(o.get('stopBits', 1)),
                    parity={'none': 'N', 'even': 'E', 'odd': 'O'}[o.get('parity', 'none')],
                    rtscts=o.get('flowControl') == 'hardware', timeout=.015, write_timeout=2)
                return {'opened': True}
        port = self.ports.get(key)
        if port is None:
            if action == 'close':
                return {'closed': True}
            raise ValueError('串口未打开')
        if action == 'read':
            data = port.read(1)
            if data:
                data += port.read(min(port.in_waiting, 262143))
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
            port.close()
            with self.port_lock:
                self.ports.pop(key, None)
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
        try:
            handlers = {'usb': proxy.usb_call, 'hid': proxy.hid_call, 'serial': proxy.serial_call}
            if kind not in handlers:
                raise ValueError('未知本地探针通路')
            return jsonify(ok=True, value=handlers[kind](action, value))
        except Exception as error:
            return jsonify(ok=False, error=str(error), type=type(error).__name__), 400

    return proxy
