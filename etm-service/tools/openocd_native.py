"""OpenOCD Wasm target memory on the native capture's existing USB lease."""
import json
from pathlib import Path
from queue import Empty, Queue
import shutil
import struct
import subprocess
import threading
import time

import usb.core
from native_probe import reset_dap_session

WORKER = Path(__file__).with_name('openocd-native.mjs')
IMAGE_CHUNK = 16 * 1024


def node_runtime():
    node = shutil.which('node')
    if node is None or not WORKER.is_file():
        raise RuntimeError('原生 Trace 目标控制需要 Node.js 和 OpenOCD Wasm 工作区')
    return node


class WasmMemory:
    def __init__(self, dev, out, inp, clock_khz):
        self.dev, self.out, self.inp = dev, out, inp
        self.clock_khz = clock_khz
        self.process = None
        self.sequence = 0
        self.lock = threading.Lock()
        if (out.bEndpointAddress, inp.bEndpointAddress) != (2, 0x81):
            raise ValueError('Zynq DAP 端点须为 OUT2 / IN1')

    def _start(self):
        self.lines = Queue()
        self.process = subprocess.Popen([node_runtime(), str(WORKER)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, text=True, encoding='utf-8',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def receive(stdout, lines):
            for line in stdout:
                lines.put(line)
            lines.put(None)
        threading.Thread(target=receive, args=(self.process.stdout, self.lines), daemon=True).start()

    def _send(self, value):
        self.process.stdin.write(json.dumps(value, separators=(',', ':')) + '\n')
        self.process.stdin.flush()

    def _request(self, op, **payload):
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            self._send(dict(id=request_id, op=op, **payload))
            until = time.monotonic() + 30
            while True:
                try:
                    line = self.lines.get(timeout=max(0, until - time.monotonic()))
                except Empty:
                    self.process.kill()
                    raise RuntimeError('OpenOCD Wasm 控制超时；未重放') from None
                if line is None:
                    raise RuntimeError('OpenOCD Wasm 控制进程已退出')
                reply = json.loads(line)
                if 'usb' in reply:
                    call = reply['usb']
                    try:
                        result = {'value':self._usb(call['method'], call['args'])}
                    except Exception as error:
                        result = {'error':str(error)}
                    self._send({'usbReply':dict(id=call['id'], **result)})
                    continue
                if reply.get('id') != request_id:
                    raise RuntimeError('OpenOCD Wasm 回包 ID 不符')
                if 'error' in reply:
                    raise RuntimeError(reply['error'])
                return reply.get('value')

    def _usb(self, method, args):
        if method == 'open':
            return self.dev.get_active_configuration().bConfigurationValue
        if method == 'close':
            return None  # The outer capture still owns the handle and EP2 IN.
        if method == 'configuration' and args == [1]:
            if self.dev.get_active_configuration().bConfigurationValue != 1:
                raise ValueError('OpenOCD 不能切换采集 USB 配置')
            return None
        if method == 'claim' and args == [0]:
            try:
                self.dev.ctrl_transfer(0xc0, 0x5b, 0x4441, 0x5052, 32, timeout=2000)
            except usb.core.USBError as error:
                if error.backend_error_code != -9:  # Legacy firmware lacks the epoch request.
                    raise
            else:
                reset_dap_session(self.dev)
            return None
        if method == 'release' and args == [0]:
            return None
        if method == 'descriptor':
            setup, length = args
            if (setup['requestType'],setup['recipient'],setup['request']) != ('standard','device',6) or \
                    setup['value'] >> 8 not in (1,2,3) or not 1 <= length <= 4096:
                raise ValueError('只允许读取标准 USB 描述符')
            return bytes(self.dev.ctrl_transfer(0x80,6,setup['value'],setup['index'],length,timeout=2000)).hex()
        if method == 'write' and args[0] == 2:
            data = bytes.fromhex(args[1])
            written = self.out.write(data, timeout=2000)
            if written != len(data):
                raise ValueError('OpenOCD DAP 短写；未重放')
            if 0 < len(data) < 4096 and len(data) % self.out.wMaxPacketSize == 0:
                self.out.write(b'', timeout=2000)
            return written
        if method == 'read' and args[0] == 1 and 1 <= args[1] <= 4096:
            return bytes(self.inp.read(args[1], timeout=2000)).hex()
        raise ValueError('OpenOCD USB 操作不在采集租约内')

    def open(self):
        self._start()
        try:
            return self._request('open',clockKhz=self.clock_khz,identity={
                'vendorId':self.dev.idVendor,'productId':self.dev.idProduct,
                'serialNumber':self.dev.serial_number,'productName':self.dev.product})
        except BaseException:
            self.close(graceful=False)
            raise

    def close(self, graceful=True):
        process = self.process
        if process is None:
            return
        try:
            if graceful and process.poll() is None:
                self._request('close')
        finally:
            if process.poll() is None:
                process.stdin.close()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdin.close()
            process.stdout.close()
            self.process = None

    def reconnect(self):
        self.close(graceful=False)
        return self.open()

    def read(self, address, length):
        if not 0 <= address <= 0xffffffff or not 0 <= length <= 0x100000000-address:
            raise ValueError('目标内存范围越界')
        result = bytearray()
        for offset in range(0,length,IMAGE_CHUNK):
            size = min(IMAGE_CHUNK,length-offset)
            chunk = bytes.fromhex(self._request('read',address=address+offset,length=size))
            if len(chunk) != size:
                raise RuntimeError('OpenOCD Wasm 内存短读')
            result.extend(chunk)
        return bytes(result)

    def write(self, address, data):
        if not 0 <= address <= 0xffffffff or len(data) > 0x100000000-address:
            raise ValueError('目标内存范围越界')
        for offset in range(0,len(data),IMAGE_CHUNK):
            self._request('write',address=address+offset,data=bytes(data[offset:offset+IMAGE_CHUNK]).hex())

    def word(self, address):
        return struct.unpack('<I',self.read(address,4))[0]

    def write_word(self, address, value):
        self.write(address,struct.pack('<I',value))
