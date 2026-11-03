"""Private native sessions; only bounded JSON DTOs cross the service boundary."""
import atexit
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import secrets
import time
from types import SimpleNamespace
import weakref

import trace_store as ts

_CLIENTS = weakref.WeakSet()


class Client:
    def __init__(self, command, *args, timeout=120):
        import native_storebuild
        self.lock = threading.RLock()
        self.responses = queue.Queue()
        self.timeout = timeout
        self.closed = False
        self.log = tempfile.TemporaryFile('w+b')
        self.process = self.reader = None
        try:
            self.process = subprocess.Popen([str(native_storebuild.binary_path()), command, *map(str, args)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            _CLIENTS.add(self)
            self.reader = threading.Thread(target=self._pump,
                args=(self.process.stdout, self.responses), daemon=True, name='native-etm-response')
            self.reader.start()
            self.ready = self.receive()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _pump(stream, responses):
        try:
            while True:
                line = stream.readline((128 << 20) + 1)
                if not line:
                    break
                if len(line) > 128 << 20 or not line.endswith(b'\n'):
                    responses.put(ValueError('Native response exceeds framing limit'))
                    return
                responses.put(json.loads(line.decode('utf8')))
        except BaseException as error:
            responses.put(error)
        finally:
            responses.put(EOFError('Native core exited'))

    def receive(self):
        try:
            value = self.responses.get(timeout=self.timeout)
        except queue.Empty as error:
            self.close()
            raise ts.TraceStoreError('原生核心查询超时，已停止本次worker') from error
        if isinstance(value, BaseException):
            self.log.seek(0)
            detail = self.log.read(8192).decode('utf8', 'replace')
            raise ts.TraceStoreError('%s：%s' % (value, detail))
        if not isinstance(value, dict) or not value.get('ok'):
            raise ts.TraceStoreError((value or {}).get('error', '原生核心响应无效'))
        return value

    def call(self, op, **arguments):
        with self.lock:
            if self.closed:
                raise ts.TraceStoreError('原生核心会话已关闭')
            try:
                data = json.dumps(dict(op=op, **arguments), ensure_ascii=False).encode('utf8') + b'\n'
                if len(data) > 16 << 20:
                    raise ts.TraceStoreError('原生核心请求超过16MiB')
                self.process.stdin.write(data)
                self.process.stdin.flush()
                return self.receive()['result']
            except (BrokenPipeError, OSError) as error:
                self.close()
                raise ts.TraceStoreError('原生核心通信中断') from error

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                if self.process is not None:
                    if self.process.stdin:
                        self.process.stdin.close()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=10)
            finally:
                if self.reader is not None and self.reader.ident is not None:
                    self.reader.join(timeout=2)
                if self.process is not None and self.process.stdout:
                    self.process.stdout.close()
                self.log.close()
                _CLIENTS.discard(self)


@atexit.register
def close_clients():
    for client in list(_CLIENTS):
        client.close()


class Image:
    """Presentation compatibility for ELF users; parsing and lookups are native."""
    def __init__(self, path, sources=None):
        self.path = Path(path)
        self.source_text = dict(sources or {})
        self.client = Client('image-server', self.path.resolve())
        info = self.client.ready['image']
        self.sha256 = info['sha256']
        self.functions = [tuple(v) for v in info['functions']]
        self.starts = [v[0] for v in self.functions]
        self.lines = {v[0]: tuple(v[1:]) for v in info['lines']}
        self.line_starts = list(self.lines)
        self._segments = info['segments']
        self._breakpoint_starts = None
        self.preparation = dict(native=True, cacheHit=False, sha256=self.sha256)

    @property
    def bytes(self):
        return self.path.read_bytes()

    @property
    def elf(self):
        return self

    @property
    def segments(self):
        return [(v['address'], bytes.fromhex(v['data'])) for v in self.client.call('segments')]

    def iter_segments(self):
        for info in self.client.call('segments'):
            value = dict(p_type='PT_LOAD', p_vaddr=info['address'], p_paddr=info['physical'],
                         p_flags=info['flags'], p_filesz=info['size'], p_memsz=info['memory'])
            data = bytes.fromhex(info['data'])
            class Segment(dict):
                def data(self):
                    return self.payload
            segment = Segment(value)
            segment.payload = data
            yield segment

    def __getitem__(self, key):
        return {'e_machine': 'EM_ARM'}[key]

    @property
    def little_endian(self):
        return True

    def read(self, address, size):
        return bytes.fromhex(self.client.call('read', address=int(address), size=int(size)))

    def location(self, address):
        return tuple(self.client.call('location', address=int(address)))

    def breakpoint_starts(self):
        if self._breakpoint_starts is None:
            self._breakpoint_starts = frozenset(self.client.call('breakpoint-starts'))
        return self._breakpoint_starts

    def source(self, file):
        from decode_trace import ROOT
        return self.client.call('source', file=file, sources=self.source_text, root=str(ROOT / 'firmware'))

    def elf_info(self):
        return self.client.call('elf-info')

    def close(self):
        if hasattr(self, 'client'):
            self.client.close()

    def __del__(self):
        self.close()


class Container:
    def __init__(self, snapshot):
        self.path = Path(snapshot['path'])
        self.generation_tag = int(snapshot['manifest']['generationTag'], 0)
        self.blocks = [SimpleNamespace(**b) for b in snapshot['blocks']]

    def of_type(self, kind):
        return [i for i, block in enumerate(self.blocks) if block.block_type == kind]


class Store:
    """RecordStore API backed entirely by an immutable C++ reader generation."""
    def __init__(self, folder, verify='full', verify_crc=True):
        self.folder = Path(folder).resolve()
        self.client = Client('query-server', self.folder / 'manifest.json')
        ready = self.client.ready
        if ready.get('protocol') != 'etm-query/1':
            self.close()
            raise ts.TraceStoreError('原生查询协议不匹配')
        snapshot = ready['snapshot']
        self.manifest, self.meta, self.summary, self.sources = (
            snapshot[k] for k in ('manifest', 'meta', 'summary', 'sources'))
        self.generation = self.manifest['generation']
        self.counts = self.meta['counts']
        self.first_seq, self.last_seq = self.meta['seq']['first'], self.meta['seq']['last']
        self.container = Container(snapshot)
        self.query_index = SimpleNamespace(meta=snapshot['queryMeta'], _row_state=True)
        self._stats = snapshot['stats']
        self._static = self._strings = None

    @property
    def static(self):
        with self.client.lock:
            if self._static is None:
                values = []
                for value in self.client.call('static'):
                    value['bytes'] = bytes.fromhex(value['bytes'])
                    values.append(SimpleNamespace(**value))
                self._static = values
            return self._static

    @property
    def static_by_pc(self):
        return {entry.pc: n for n, entry in enumerate(self.static)}

    @property
    def strings(self):
        with self.client.lock:
            if self._strings is None:
                self._strings = self.client.call('strings')
            return self._strings

    def overview(self):
        return self.client.call('overview')

    def stats(self):
        return self.client.call('stats')

    def page(self, view='events', offset=0, limit=150, search='', hide_skipped=False, start=None, end=None):
        return self.client.call('page', view=view or 'events', offset=int(offset), limit=int(limit),
            search=search or '', hide_skipped=bool(hide_skipped), start=_integer(start), end=_integer(end))

    def event(self, seq):
        return self.client.call('event', seq=int(seq))

    def events(self, start=None, end=None):
        lo = self.first_seq if start is None else max(self.first_seq, int(start))
        hi = self.last_seq if end is None else min(self.last_seq, int(end))
        if hi < lo:
            raise ts.TraceStoreError('区间结束 seq 不能小于起点')
        while lo <= hi:
            rows = self.client.call('events', start=lo, end=hi)
            if not rows:
                break
            yield from rows
            lo = rows[-1]['seq'] + 1

    def first(self):
        return self.first_seq

    def last(self):
        return self.last_seq

    def bounds(self):
        return [self.first_seq, self.last_seq]

    def window(self, start=None, end=None, bins=1200):
        return self.client.call('window', start=_integer(start), end=_integer(end), bins=int(bins))

    def function_timeline(self, start=None, end=None, search='', hide_skipped=False, bins=1600, max_functions=6):
        return self.client.call('function_timeline', start=_integer(start), end=_integer(end),
            search=search or '', hide_skipped=bool(hide_skipped), bins=int(bins), max_functions=int(max_functions))

    def navigate(self, seq=0, direction=1, mode='instruction', pc=None, start=None, end=None):
        return self.client.call('navigate', seq=int(seq), direction=int(direction), mode=mode,
            pc=_integer(pc), start=_integer(start), end=_integer(end))

    def issues(self, offset=0, limit=100):
        return self.client.call('issues', offset=int(offset), limit=int(limit))

    @property
    def issues_list(self):
        values, offset = [], 0
        while True:
            page = self.issues(offset, 500)
            values.extend(page['rows'])
            offset += len(page['rows'])
            if offset >= page['total']:
                return values

    def source(self, file):
        return self.client.call('source', file=file)

    def seq_position(self, seq):
        return self.client.call('position', seq=int(seq))

    def capture_start(self, pc):
        return self.client.call('capture-start', pc=int(pc))

    def close(self):
        if hasattr(self, 'client'):
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()


def _integer(value):
    return None if value is None else int(value)


def reader(folder, **options):
    return Store(folder, **options) if os.environ.get('ETM_NATIVE_QUERY', '1') != '0' else ts.TraceStore(folder, **options)


def reindex(folder, container='v2'):
    from trace_store_adapter import verify_inputs
    folder = Path(folder).resolve()
    record = folder.parent if folder.name == 'store' else folder
    if folder.name != 'store':
        folder /= 'store'
    generation = 'g-%s-%s' % (time.strftime('%Y%m%dT%H%M%S'), secrets.token_hex(4))
    tag = secrets.randbits(63) or 1
    published = False
    try:
        with Store(folder) as store:
            original = store.generation
            verification = verify_inputs(record, store.manifest)
            if verification['problems']:
                raise ts.TraceStoreError('当前输入与待重建索引的库不一致')
            result = store.client.call('reindex', generation=generation, tag=tag, container=container)
            if verify_inputs(record, store.manifest)['problems']:
                raise ts.TraceStoreError('输入在索引构建期间变化')
            current = json.loads((folder / 'manifest.json').read_text(encoding='utf8'))
            if current['generation'] != original:
                raise ts.TraceStoreError('索引构建期间记录已换代，拒绝覆盖')
            ts._publish_manifest(folder, result['manifest'])
            published = True
            return dict(ok=True, storeDir=str(folder), generation=generation,
                        queryIndex=result['queryIndex'], seconds=result['seconds'],
                        counts=result['manifest']['counts'], container=container, engine='native')
    finally:
        if not published:
            ts._remove_tree(folder / 'generations' / generation)
