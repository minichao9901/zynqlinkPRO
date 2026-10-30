"""Kingst-LA-compatible shim that captures ZynqDAP's parallel ETM stream.

The superlink ETM server drives a Kingst VIS socket from `capture_job`. This
module keeps that job/record/decode pipeline unchanged but replaces the LA:
`Vis.cmd()` accepts the LA configuration commands, `sock.sendall(b'start')`
arms the Zynq FPGA ETM receiver and resumes the target CPU, and `recv()`
returns once the ending ZET1 packet arrives. `do_export()` writes the
demultiplexed source-ID-2 bytes to `capture.bin`; `decode_stream()` then feeds
those bytes to OpenCSD exactly like an imported ETM BIN record.
"""
import struct
import threading
import time

import usb.core
import usb.util

from dap_pipeline_bench import open_dap, setup, xfer, le

TRACE_EP = 0x82
CTRL_REQUEST = 0x60
CTRL_REFERENCE = 0x61
CTRL_INDEX = 0x4554
ZET1_MAGIC = 0x3154455A
ETM_SIGNATURE = 0x45544D31


class CaptureError(RuntimeError):
    pass


def _quality():
    return {"records": 0, "loss": False, "synced": False, "ended": False,
            "fclk": 0, "tckKhz": None, "captureId": None}


class Session:
    """One open ZynqDAP handle and at most one ETM capture."""

    def __init__(self):
        self.dev = None
        self.out = None
        self.inp = None
        self.lock = threading.Lock()
        self.config = {}
        self.traceid = 2
        self.seconds = 0.01
        self.bytes = bytearray()
        self.quality = _quality()
        self.error = None
        self.running = False
        self.done = threading.Event()
        self.started = 0.0
        self._reader = None
        self._timer = None

    # ---------------- USB ----------------
    def open(self):
        if self.dev is not None:
            return
        self.dev, self.out, self.inp = open_dap()
        setup(self.out, self.inp, 1000)
        self._dap_write32(0xE000EDF0, 0xA05F0003)   # keep the target halted

    def close(self):
        with self.lock:
            if self.running:
                return
        if self.dev is None:
            return
        try:
            usb.util.release_interface(self.dev, 0)
        except Exception:
            pass
        try:
            usb.util.dispose_resources(self.dev)
        except Exception:
            pass
        self.dev = self.out = self.inp = None

    def _control(self, action=0):
        reply = self.dev.ctrl_transfer(0xC0, CTRL_REQUEST, action, CTRL_INDEX, 32, timeout=2000)
        if len(reply) != 32:
            raise CaptureError("ETM 控制请求返回 %d 字节" % len(reply))
        return list(struct.unpack("<8I", bytes(reply)))

    def _reference_clock(self):
        reply = bytes(self.dev.ctrl_transfer(0xC0, CTRL_REFERENCE, 0, CTRL_INDEX, 16, timeout=2000))
        if len(reply) != 16:
            raise CaptureError("ETM 参考时钟请求返回 %d 字节" % len(reply))
        return struct.unpack("<I", reply[:4])[0]

    def _set_tar(self, addr):
        xfer(self.out, self.inp, [5, 0, 3, 8] + le(0) + [1] + le(0x23000052) + [5] + le(addr))

    def _dap_write32(self, addr, value):
        self._set_tar(addr)
        reply = xfer(self.out, self.inp, [6, 0, 1, 0, 0x0D] + le(value))
        # DAP_TransferBlock reply: [cmd, count_lo, count_hi, ack]; ack is byte 3.
        if len(reply) < 4 or reply[1] != 1 or (reply[3] & 7) != 1:
            raise CaptureError("DAP 写 %#x 失败：%s" % (addr, reply[:8].hex()))

    def _dap_read32(self, addr):
        self._set_tar(addr)
        reply = xfer(self.out, self.inp, [6, 0, 1, 0, 0x0F])
        if len(reply) < 8 or reply[1] != 1 or (reply[3] & 7) != 1:
            raise CaptureError("DAP 读 %#x 失败：%s" % (addr, reply[:8].hex()))
        return struct.unpack_from("<I", reply, 4)[0]

    def _restart_trace(self):
        """Force a fresh TPIU sync inside the FPGA capture window.

        The page enables ETM while the CPU is still halted, then hands USB to
        this service. Arming after that can start mid-frame; writing PROG and
        re-enabling ETM emits a new sync sequence before the CPU resumes.
        """
        if str(self.config.get("protocol", "")).lower() != "etmv3":
            return
        ctrl = int(self.config.get("ctrl", 0))
        try:
            self._dap_write32(0xE0041FB0, 0xC5ACCE55)      # ETM LAR; TPIU LAR is 0xE0040FB0
            self._dap_write32(0xE0041000, (ctrl | 0x400) & 0xFFFFFFFF)
            for _ in range(100):
                if self._dap_read32(0xE0041010) & 2:
                    break
                time.sleep(0.002)
            else:
                raise CaptureError('ETM没有进入编程模式，拒绝继续采集')
            self._dap_write32(0xE0041000, ctrl & ~0x400)
            for _ in range(100):
                if not (self._dap_read32(0xE0041010) & 2):
                    break
                time.sleep(0.002)
            else:
                raise CaptureError('ETM没有退出编程模式，拒绝继续采集')
        except CaptureError:
            raise

    # ---------------- capture ----------------
    def configure(self, config, traceid, seconds):
        self.config = dict(config or {})
        self.traceid = int(traceid or self.config.get("traceid") or 2)
        self.seconds = float(seconds or 0.01)

    def start(self):
        self.open()
        self.bytes = bytearray()
        self.quality = _quality()
        self.error = None
        self.done.clear()
        state = self._control()
        if state[0] != ETM_SIGNATURE:
            raise CaptureError("ETM PL 签名不匹配，请核对 bit/ELF 配对")
        ref = self._reference_clock()
        if not 190_000_000 <= ref <= 210_000_000:
            raise CaptureError("独立采样参考时钟未初始化到 200 MHz 范围")
        self._control(0x301)
        for _ in range(100):
            state = self._control()
            if (state[1] & 1) and (state[1] & 16) and not state[7]:
                break
            time.sleep(0.005)
        else:
            raise CaptureError("ETM 采样延时校准未就绪，请核对 bit/ELF 与 PS 初始化")
        # The browser released the probe at halt; re-enable ETM after arming so
        # the TPIU sync sequence lands inside this capture, then resume the CPU.
        self._restart_trace()
        self._dap_write32(0xE000EDF0, 0xA05F0001)
        self.started = time.time()
        self.running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        if self.seconds > 0:
            self._timer = threading.Timer(self.seconds, self.stop)
            self._timer.daemon = True
            self._timer.start()
        return self

    def _read_loop(self):
        seq = None
        pending = b""
        try:
            while self.running:
                try:
                    chunk = bytes(self.dev.read(TRACE_EP, 8192, timeout=300))
                except usb.core.USBTimeoutError:
                    continue
                pending += chunk
                while len(pending) >= 32:
                    magic, pseq, flags, count = struct.unpack_from("<4I", pending, 0)
                    if magic != ZET1_MAGIC or struct.unpack_from("<I", pending, 28)[0] != 1:
                        raise CaptureError("不是 ZynqDAP ZET1 trace 数据")
                    length = 32 + count * 2
                    if len(pending) < length:
                        break
                    fclk = struct.unpack_from("<I", pending, 20)[0]
                    capture_id = struct.unpack_from("<I", pending, 24)[0]
                    if seq is not None and pseq != ((seq + 1) & 0xFFFFFFFF):
                        self.quality["loss"] = True
                    seq = pseq
                    self.quality["records"] += count
                    self.quality["fclk"] = fclk
                    self.quality["tckKhz"] = flags >> 16 or None
                    self.quality["captureId"] = capture_id
                    self.quality["loss"] |= bool(flags & 4)
                    self.quality["synced"] |= bool(flags & 2)
                    records = pending[32:length]
                    for i in range(0, len(records), 2):
                        if records[i + 1] == self.traceid:
                            self.bytes.append(records[i])
                    pending = pending[length:]
                    if flags & 8:
                        self.quality["ended"] = True
                        self.running = False
                        break
                if self.quality["ended"]:
                    break
        except Exception as exc:
            self.error = str(exc)
            self.running = False
        finally:
            self.done.set()

    def stop(self):
        if not self.running and self.done.is_set():
            return
        try:
            self._control(2)
        except Exception as exc:
            self.error = self.error or str(exc)
        if self._reader:
            self._reader.join(timeout=6)
        self.running = False
        self.done.set()

    def wait(self, timeout=None):
        return self.done.wait(timeout)


_session = None
_session_lock = threading.Lock()


def session():
    global _session
    with _session_lock:
        if _session is None:
            _session = Session()
        return _session


def release():
    global _session
    with _session_lock:
        if _session is not None:
            _session.stop()
            _session.close()
            _session = None


class _Sock:
    """The tiny socket surface `capture_job` uses (sendall/recv/timeout)."""

    def __init__(self, vis):
        self.vis = vis
        self._replied = False
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, data):
        if data != b"start":
            raise CaptureError("unsupported LA start command")
        s = session()
        s.configure(self.vis.config, self.vis.traceid, self.vis.seconds)
        s.start()
        s.wait(5)

    def recv(self, n):
        s = session()
        if not s.wait(self.timeout if self.timeout else None):
            raise TimeoutError("ETM capture timeout")
        if s.error:
            raise CaptureError(s.error)
        if self._replied:
            return b""
        self._replied = True
        return b"ACK"

    def shutdown(self, how):
        try:
            session().stop()
        except Exception:
            pass

    def close(self):
        pass


class Vis:
    """Drop-in replacement for the Kingst VIS client used by server.py."""

    def __init__(self, *args, **kwargs):
        self.config = {}
        self.traceid = 2
        self.seconds = 0.01
        self.rate = 500_000_000
        self.sock = _Sock(self)
        self._closed = False

    def cmd(self, text, timeout=None):
        parts = str(text).split()
        if not parts:
            return ""
        head = parts[0]
        if head == "get-supported-sample-rate":
            return "100000000 200000000 500000000"
        if head == "set-sample-rate":
            self.rate = int(float(parts[1]))
            return "OK"
        if head == "set-sample-time":
            self.seconds = float(parts[1])
            return "OK"
        if head in ("set-threshold-voltage", "set-trigger"):
            return "OK"
        if head == "start":
            self.sock.sendall(b"start")
            return "ACK"
        if head == "stop":
            session().stop()
            return "ACK"
        if head == "get-actual-sample-depth":
            return str(int(self.seconds * self.rate))
        if head == "get-actual-sample-time":
            return str(self.seconds)
        return "OK"

    def close(self):
        # The capture job calls close() right after ACK, before do_export()
        # reads the buffer. Keep the handle until do_export() has written the
        # bytes and released the interface for the browser.
        self._closed = True


def do_export(vis, path, channels):
    """Write demultiplexed ETM bytes; `channels` is ignored (LA-only concept)."""
    s = session()
    s.wait(5)
    if s.error:
        raise CaptureError(s.error)
    with open(path, "wb") as f:
        f.write(bytes(s.bytes))
    # The browser is waiting to reconnect; release the interface before the
    # (potentially slow) native decode starts.
    release()


def read_glitch_settings(path, rate):
    return {"basis": "zynq-etm", "enabled": False, "ns": 0,
            "note": "Zynq FPGA receives four-bit DDR directly; no LA glitch filter"}
