"""Repeatable real-Web acceptance through toolbox's authenticated page queue."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time
import sys

ROOT = Path(__file__).resolve().parents[1]


class Acceptance:
    def __init__(self, args):
        from toolbox import Client
        self.args = args
        self.out = Path(args.artifacts).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.client = Client(args.runtime, args.case_timeout)
        self.steps = []

    def save(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

    def call(self, payload):
        started = time.perf_counter()
        result = self.client.request(payload)
        recorded=copy.deepcopy(result)
        if payload.get('op')=='download' and isinstance(recorded.get('value'),dict) and 'base64' in recorded['value']:
            encoded=recorded['value'].pop('base64')
            raw=base64.b64decode(encoded)
            recorded['value']['downloadEvidence']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        self.steps.append({'request': payload if payload.get('action') != 'elf' else {'action': 'elf', 'name': payload['name']},
                           'seconds': time.perf_counter() - started, 'result': recorded})
        # Do not duplicate uploaded firmware/source contents in the step log.
        if payload.get('op') == 'upload':
            self.steps[-1]['request'] = {k: v for k, v in payload.items() if k != 'files'}
        self.save(self.out / 'steps.json', self.steps)
        self.client.http('ack/' + result['job'], {})
        if not result.get('ok'):
            raise RuntimeError(result.get('error') or str(result))
        value = result.get('value')
        if isinstance(value, dict) and value.get('returned'):
            if value.get('errors'):
                raise RuntimeError('Browser errors: ' + str(value['errors']))
            return value.get('value')
        return value

    def page(self, page, op, **fields):
        return self.call({'action': 'workbench', 'page': page, 'op': op, **fields})

    def wait(self, page, selector, contains):
        end = time.monotonic() + 30
        while True:
            value = self.page(page, 'read', selector=selector)
            if contains in value['text']:
                return value
            if time.monotonic() > end:
                raise TimeoutError('Web控件未完成：' + selector)
            time.sleep(.1)

    def ready(self, page, selector):
        end = time.monotonic() + 45
        while True:
            value = self.page(page, 'read', selector=selector)
            if value.get('disabled') is False:
                return
            if time.monotonic() > end:
                raise TimeoutError('Web仍忙：' + selector)
            time.sleep(.1)

    def load_etm(self):
        from toolbox import pack_file
        elf = Path(self.args.elf).resolve()
        self.page('etm', 'upload', selector='#elf-file', files=[pack_file(elf)])
        self.ready('etm', '#hse')
        self.wait('etm', '#elf-label', elf.name)
        if self.args.sources:
            source = Path(self.args.sources).resolve()
            files = sorted(p for p in source.rglob('*') if p.is_file())
            self.page('etm', 'upload', selector='#sources-files',
                      files=[pack_file(f, source.name + '/' + f.relative_to(source).as_posix()) for f in files])
            self.ready('etm', '#hse')
            self.wait('etm', '#sources-label', '已保存本地快照')
        self.page('etm', 'set', selector='#hse', value=8)
        self.page('etm', 'set', selector='#reset-before', value=False)
        self.page('etm', 'set', selector='#break-command', value='b cdc_poll')
        self.page('etm', 'click', selector='#add-break')
        self.wait('etm', '#breakpoint-list', 'cdc_poll')

    def capacity(self):
        self.load_etm()
        rows = []
        for seconds in [float(x) for x in self.args.lengths.split(',')]:
            started = time.perf_counter()
            captured = self.page('etm', 'invoke', method='captureNative', args=[{
                'seconds': seconds, 'entry': 'cdc_poll', 'resetToEntry': False,
                'hclkDiv': 4, 'gpioSpeed': 1, 'traceId': 2, 'swdKhz': 1000, 'decode': True}])
            wall = time.perf_counter() - started
            sid = captured['record']
            folder = ROOT / 'etm-service/records' / sid
            if not folder.is_dir():
                raise RuntimeError('记录不在此工作区；请核对服务与源码目录')
            metadata = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
            decoded = json.loads((folder / 'decoded.json').read_text(encoding='utf-8'))
            quality = metadata['quality']
            dq = decoded['quality']
            passed = (quality['synced'] and quality['ended'] and not quality['loss'] and
                      captured['targetRestored'] and not dq['packetIssues'] and not dq['unprocessedBytes'] and
                      not dq['unaccountedBytes'] and not decoded['status']['lastErrorCode'] and decoded['summary']['instructions'] > 0)
            row = {'requestedSeconds': seconds, 'wallSecondsIncludingWeb': wall, 'record': sid, 'ok': bool(passed),
                   'etmBytes': (folder / 'capture.bin').stat().st_size, 'captureQuality': quality,
                   'decodedQuality': dq, 'summary': decoded['summary'], 'captureExtent': metadata.get('captureExtent')}
            performance = folder / 'decode-performance.json'
            if performance.is_file():
                row['processing'] = json.loads(performance.read_text())
            evidence = self.out / ('window-' + str(round(seconds * 1000)) + 'ms')
            evidence.mkdir()
            for source, destination in [('session.json', 'session.json'), ('raw/acceptance.json', 'acceptance.json'),
                                        ('capture.bin', 'capture.etm')]:
                shutil.copy2(folder / source, evidence / destination)
            self.save(evidence / 'summary.json', row)
            rows.append(row)
            self.save(self.out / 'results.json', {'suite': 'capacity', 'rows': rows})
            print(f"{seconds*1000:g}ms: {row['etmBytes']} ETM bytes, {decoded['summary']['instructions']} paths, {wall:.2f}s, ok={passed}", file=sys.stderr, flush=True)
            if not passed:
                raise RuntimeError('窗口质量未通过；未自动重试')
        return {'ok': True, 'suite': 'capacity', 'rows': rows, 'artifacts': str(self.out)}

    def debug(self):
        elf = Path(self.args.elf)
        self.call({'action': 'disconnect'})
        self.call({'action': 'connect', 'swdHz': 1000000})
        self.call({'action': 'elf', 'name': elf.name, 'data': base64.b64encode(elf.read_bytes()).decode('ascii')})
        rows = []
        try:
            for index in range(self.args.rounds):
                started = time.perf_counter()
                self.call({'action': 'command', 'commands': ['halt', 'bd all', 'b cdc_poll', 'c']})
                halted = self.call({'action': 'wait-halt', 'timeoutMs': 3000})
                stepped = self.call({'action': 'command', 'commands': ['r r0', 'si', 'si', 'bd all', 'c']})
                rows.append({'round': index, 'seconds': time.perf_counter() - started, 'halted': halted,
                             'status': stepped['status']})
                self.save(self.out / 'results.json', {'suite': 'debug', 'rows': rows})
        finally:
            self.call({'action': 'command', 'commands': ['bd all', 'c']})
            self.call({'action': 'disconnect'})
        return {'ok': True, 'suite': 'debug', 'rounds': len(rows), 'artifacts': str(self.out)}


def run(args):
    if not Path(args.elf).is_file():
        raise ValueError('验收ELF不存在')
    lengths = [float(x) for x in args.lengths.split(',')]
    if any(not 0 < x <= 1 for x in lengths) or not 1 <= args.rounds <= 1000:
        raise ValueError('窗口必须为0..1秒、轮数为1..1000')
    acceptance = Acceptance(args)
    try:
        result = getattr(acceptance, args.suite)()
    except Exception as error:
        acceptance.save(acceptance.out / 'failure.json', {'ok': False, 'error': str(error), 'steps': len(acceptance.steps)})
        raise
    acceptance.save(acceptance.out / 'summary.json', result)
    return result
