"""Exercise the capture job's record/decode plumbing without USB.

The real ZynqDAP is not on the bus right now (only an akaLinkPro), so this
replaces `Vis` and `do_export` with sample ETM bytes and drives the exact
server `capture_job` path used by /api/capture.
"""
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r'E:\zynqlinkPRO\etm-service')
sys.path.insert(0, r'E:\zynqlinkPRO\etm-service\tools')

import server

root = Path(r'E:\zynqlinkPRO')
etm = (Path(__file__).parent / 'fixtures/f103ze-1309.etm').read_bytes()
config = json.loads((Path(__file__).parent / 'fixtures/f103ze-config.json').read_text(encoding='utf-8'))
elf = root / 'etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf'


class FakeSock:
    def settimeout(self, value): pass
    def sendall(self, data):
        if data != b'start':
            raise RuntimeError(data)
    def recv(self, n): return b'ACK'
    def shutdown(self, how): pass


class FakeVis:
    def __init__(self):
        self.config = config
        self.traceid = 2
        self.seconds = 0.01
        self.sock = FakeSock()
    def cmd(self, text, timeout=None):
        head = str(text).split()[0]
        if head == 'get-supported-sample-rate': return '500000000'
        if head == 'get-actual-sample-depth': return str(int(self.seconds * 500_000_000))
        if head == 'get-actual-sample-time': return str(self.seconds)
        return 'OK'
    def close(self): pass


server.Vis = FakeVis
server.do_export = lambda vis, path, channels: Path(path).write_bytes(etm)

sid = 'capture-fake-' + str(int(time.time()))
jid = server.new_job(sid, 'queued')
folder = server.directory(sid)
folder.mkdir()
(folder / 'firmware.elf').write_bytes(elf.read_bytes())
options = dict(rate=500_000_000, seconds=0.01, threshold=1.65, sync=True, decode=True,
               clock=0, data=[1, 2, 3, 4], config=config, elfId='elf-fake',
               targetVerified=True, fraction=0.25, glitchNs=0, targetSnapshot={'name': 'fake'},
               captureScope='business-unfiltered-window', captureEntry=None,
               rawFormat='bin', libraryOrigin='validation')
server.save(sid, dict(name='fake zynq capture', created=time.time(), input='capture.bin', **options))
server.capture_job(jid, sid, options)
job = server.jobs[jid]
print('job', job.get('state'), job.get('error'))
meta = server.meta(sid)
print('input', meta.get('input'), 'bytes', (folder / 'capture.bin').stat().st_size)
decoded = folder / 'decoded.json'
print('decoded', decoded.exists())
if decoded.exists():
    data = json.loads(decoded.read_text(encoding="utf-8"))
    print('summary', json.dumps(data.get('summary'), ensure_ascii=False)[:300])


