"""Finite target-CDC echo stimulus synchronized to the FPGA capture ready marker."""
import hashlib
import json
from pathlib import Path
import threading
import time
import serial
import serial.tools.list_ports


def settings(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('serialStimulus必须为对象')
    port = value.get('port')
    if port not in {p.device for p in serial.tools.list_ports.comports()}:
        raise ValueError('刺激串口不存在')
    payload = value.get('payload', 'ETM_CDC_ECHO_0123456789abcdef\r\n')
    if not isinstance(payload, str) or not 1 <= len(payload.encode('utf-8')) <= 4096:
        raise ValueError('刺激payload必须为1..4096字节UTF-8字符串')
    rounds = value.get('rounds', 4)
    interval = value.get('intervalSeconds', .01)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 128:
        raise ValueError('刺激rounds须为1..128')
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not 0 <= interval <= 1:
        raise ValueError('刺激intervalSeconds须为0..1')
    return {'port': port, 'payload': payload, 'rounds': rounds, 'intervalSeconds': interval}


class SerialStimulus:
    def __init__(self, options, ready_file, seconds):
        self.options, self.ready_file, self.seconds = options, Path(ready_file), seconds
        self.finished = threading.Event()
        self.thread = None
        self.port = None
        self.report = {'port': options['port'], 'armed': False, 'rounds': [], 'ok': False,
                       'requestedRounds': options['rounds'], 'captureSeconds': seconds}

    def prepare(self):
        self.port = serial.Serial(self.options['port'], 115200, timeout=.15, write_timeout=1)
        self.port.reset_input_buffer()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while not self.finished.wait(.002):
                try:
                    ready = json.loads(self.ready_file.read_text())
                    if ready.get('armed'):
                        break
                except (OSError, ValueError):
                    continue
            else:
                return
            began = ready['monotonic']
            self.report['armed'] = True
            self.port.reset_input_buffer()
            payload = self.options['payload'].encode('utf-8')
            self.report['payloadBytes'] = len(payload)
            self.report['payloadSha256'] = hashlib.sha256(payload).hexdigest()
            for index in range(self.options['rounds']):
                offset = time.monotonic() - began
                if self.finished.is_set() or offset >= self.seconds:
                    break
                self.port.write(payload)
                self.port.flush()
                received = self.port.read(len(payload))
                self.report['rounds'].append({'index': index, 'sendOffsetSeconds': offset,
                    'sentBytes': len(payload), 'receivedBytes': len(received), 'byteExact': received == payload,
                    'receivedSha256': hashlib.sha256(received).hexdigest()})
                if received != payload:
                    break
                if self.finished.wait(self.options['intervalSeconds']):
                    break
            self.report['ok'] = len(self.report['rounds']) == self.options['rounds'] and all(r['byteExact'] for r in self.report['rounds'])
        except Exception as error:
            self.report['error'] = str(error)

    def close(self):
        self.finished.set()
        if self.thread:
            self.thread.join(3)
            if self.thread.is_alive():
                self.report['error'] = '串口刺激线程尚未退出'
        if self.port:
            self.port.close()
        return self.report
