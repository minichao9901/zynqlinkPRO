"""Authenticated CLI/Web capture using the existing board transaction runner.

Only enabled by an explicit probe bit/ELF pair on toolbox.py serve. Never kills
or retries the target transaction: stop waits for its bounded window/cleanup.
"""
import hmac
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from flask import abort, jsonify, request


class NativeCapture:
    def __init__(self, backend, token_file, bit, elf):
        self.backend = backend
        self.token = Path(token_file).read_text(encoding='ascii').strip()
        self.bit, self.elf = Path(bit).resolve(), Path(elf).resolve()
        if not self.bit.is_file() or not self.elf.is_file():
            raise ValueError('本地服务采集需要存在的bit/ELF配对文件；加载板卡需另行执行')

    def authorize(self):
        if request.remote_addr not in ('127.0.0.1', '::1'):
            abort(403)
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            abort(403)
        if not hmac.compare_digest(request.headers.get('X-Trace-CLI', ''), self.token):
            abort(403)

    def start(self):
        self.authorize()
        b = self.backend
        o = request.get_json()
        if not isinstance(o, dict):
            raise ValueError('采集参数必须为对象')
        elf_id = o.get('elfId')
        if not isinstance(elf_id, str) or not re.fullmatch(r'elf-[0-9a-f]{32}', elf_id):
            raise ValueError('请先在当前Web页面载入目标ELF')
        target = b.directory(elf_id) / 'firmware.elf'
        if not target.is_file():
            raise ValueError('目标ELF已失效，请在Web页面重新上传')
        b.elf_info(target)
        sources_snapshot = b.read_source_snapshot(elf_id, o['sourceSnapshot']) if o.get('sourceSnapshot') else None
        seconds = o.get('seconds', .01)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= 1:
            raise ValueError('采集时长必须大于0且不超过1秒')
        options = {'seconds': seconds, 'decode': o.get('decode', True)}
        if not isinstance(options['decode'], bool):
            raise ValueError('decode必须为boolean')
        for name, default, allowed in [('hclkDiv', 4, (1, 2, 4)), ('gpioSpeed', 1, (1, 2, 3)),
                                       ('traceId', 2, range(1, 112)), ('swdKhz', 1000, range(1, 50001))]:
            value = o.get(name, default)
            if isinstance(value, bool) or not isinstance(value, int) or value not in allowed:
                raise ValueError('无效参数：' + name)
            options[name] = value
        with b.lock:
            if any(j.get('kind', 'capture') == 'capture' and
                   (j['state'] in b.ACTIVE or j.get('_laLease') or j.get('cleanupPending')) for j in b.jobs.values()):
                raise ValueError('已有采集或清理任务，请等待完成')
            sid = 'capture-' + uuid.uuid4().hex
            jid = b.new_job(sid, 'queued')
            b.jobs[jid].update(_nativeCapture=True, _laLease=True)
        try:
            folder = b.directory(sid)
            folder.mkdir()
            shutil.copy2(target, folder / 'firmware.elf')
            sources = b.directory(elf_id) / 'sources.json'
            if sources_snapshot:
                b.save_json(folder / 'sources.json', sources_snapshot)
            elif sources.is_file():
                shutil.copy2(sources, folder / 'sources.json')
            b.save(sid, dict(name='F103ZE · local service · ' + time.strftime('%Y-%m-%d %H:%M:%S'),
                             created=time.time(), input='capture.bin', seconds=seconds,
                             captureScope='cli-web-service-continuous-window',
                             captureStatus='pending', targetVerified=False, rawFormat='bin'))
            threading.Thread(target=self.run, args=(jid, sid, options), daemon=True).start()
        except Exception as error:
            b.change(jid, state='error', error=str(error))
            with b.lock:
                b.jobs[jid].pop('_laLease', None)
            raise
        return jsonify(job=jid, record=sid)

    def run(self, jid, sid, options):
        b = self.backend
        folder = b.directory(sid)
        try:
            with b.lock:
                if b.jobs[jid].get('_stopped'):
                    b.change(jid, state='cancelled')
                    return
                b.change(jid, state='starting')
            command = [sys.executable, '-X', 'utf8', str(b.ROOT / 'trace.py'), 'capture',
                       '--elf', str(folder / 'firmware.elf'), '--out', str(folder / 'raw'),
                       '--bit', str(self.bit), '--zynq-elf', str(self.elf), '--no-decode',
                       '--seconds', str(options['seconds']), '--trace-id', str(options['traceId']),
                       '--hclk-div', str(options['hclkDiv']), '--gpio-speed', str(options['gpioSpeed']),
                       '--swd-khz', str(options['swdKhz'])]
            b.save_json(folder / 'native-command.json', command)
            # Killing the subprocess would bypass its target-restoration finally.
            # The runner bounds its capture and USB I/O; cancellation waits for it.
            process = subprocess.run(command, cwd=b.ROOT.parent, capture_output=True, text=True, encoding='utf-8')
            (folder / 'native-cli.txt').write_text(process.stdout + '\n' + process.stderr, encoding='utf-8')
            result = json.loads(process.stdout)
            if process.returncode or not result.get('ok'):
                acceptance_file = folder / 'raw/acceptance.json'
                if acceptance_file.is_file():
                    failed = b.load_json(acceptance_file)
                    if failed.get('target_cleanup_error') or failed.get('usb_cleanup_error'):
                        b.change(jid, cleanupPending=True)
                raise RuntimeError((result.get('error') or {}).get('message', '本地采集失败；原始证据保留'))
            raw = folder / 'raw'
            acceptance = b.load_json(raw / 'acceptance.json')
            if not acceptance.get('restored') or acceptance.get('target_cleanup_error'):
                b.change(jid, cleanupPending=True)
                raise RuntimeError('目标现场恢复未通过，保留原始记录；请恢复板卡后重启服务')
            metadata = b.meta(sid)
            captured = b.load_json(raw / 'session.json')
            for name in ('capture.bin', 'target-before.json', 'acceptance.json'):
                shutil.copy2(raw / name, folder / name)
            metadata.update(captured)
            metadata.update(captureStatus='saved', captureScope='cli-web-service-continuous-window',
                            configBasis='native SWD readback and ELF/Flash verification',
                            nativeAcceptance=acceptance, targetVerified=True)
            b.save(sid, metadata)
            with b.lock:
                stopped = b.jobs[jid].get('_stopped', False)
            if stopped:
                b.change(jid, state='cancelled', error='停止已完成：本次短窗与现场恢复结束，原始数据保留')
            elif options['decode']:
                b.decode_job(jid, sid)
            else:
                b.change(jid, state='done')
        except (Exception, SystemExit) as error:
            b.record_failure(sid, error, 'native capture')
            b.change(jid, state='error', error=str(error))
        finally:
            with b.lock:
                b.jobs[jid].pop('_laLease', None)

    def stop(self):
        b = self.backend
        if request.method != 'POST':
            return None
        match = re.fullmatch(r'/api/stop/([0-9a-f]{32})', request.path)
        if not match:
            return None
        with b.lock:
            job = b.jobs.get(match[1])
            if not job or not job.get('_nativeCapture'):
                return None
            self.authorize()
            pending = job['state'] in b.ACTIVE
            if pending:
                job['_stopped'] = True
            return jsonify(ok=True, stopRequested=pending, restorePending=pending,
                           note='不终止硬件事务；等当前短窗与现场恢复完成')


def install(backend, token_file, bit, elf):
    capture = NativeCapture(backend, token_file, bit, elf)
    backend.app.add_url_rule('/api/native-capture', 'native_web_capture', capture.start, methods=['POST'])
    backend.app.before_request(capture.stop)
    backend.app.extensions['native_capture'] = capture
    return capture
