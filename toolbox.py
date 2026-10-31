#!/usr/bin/env python3
"""Unified AI entry: python -X utf8 toolbox.py --help. See docs/toolbox-cli-ai.md."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import secrets
import hashlib
import subprocess
import shutil
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
PAGES = {
    'serial': ('串口助手', 'serial/assistant.js', 'ASCII/HEX/ANSI、端口、定时/快捷发送、记录、DTR/RTS'),
    'terminal': ('终端', 'serial/terminal.js', '交互终端、回显、按键/粘贴、保存'),
    'rtt': ('RTT Viewer', 'rtt/view.js', '探针/桥/模拟目标、通道、上下行、ELF、记录'),
    'rttcdc': ('RTT 转发', 'hid/stream.js', 'RTT→CDC、HID配置、接收/记录、质量报告'),
    'scope': ('J-Scope', 'scope/view.js', 'ELF变量、1–8通道、采样、触发/游标、CSV/原始数据、质量'),
    'dbg': ('调试器', 'dbg/view.js', 'ARM/RISC-V、断点/单步、寄存器/内存/变量/调用栈、异常、SVD'),
    'flash': ('烧录器', 'flash/view.js', 'ELF/HEX/BIN、目标算法、擦除/编程/校验、复位'),
    'etm': ('ETM 执行轨迹', 'etm/view.js', '目标/时钟、Zynq FPGA采集、导入/解码、全部查询/阅读/导出；另有 trace 原生CLI'),
    'gen': ('工程生成', 'gen/view.js', 'uvprojx、Makefile/脚本、参数、预览/下载'),
}


def emit(value, output=None):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if output:
        with Path(output).open('x', encoding='utf-8') as stream:
            stream.write(text + '\n')
    else:
        print(text, flush=True)


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def catalog():
    return {'protocol': 'workbench/1', 'entry': 'toolbox.py', 'guide': 'docs/toolbox-cli-ai.md',
            'pages': [{'id': key, 'label': value[0], 'source': 'web/app/' + value[1],
                       'features': value[2], 'commands': ['describe', 'state', 'show', 'read', 'set', 'click', 'interrupt', 'upload', 'invoke', 'wait', 'event', 'downloads', 'download', 'discard']}
                      for key, value in PAGES.items()],
            'trace': 'toolbox.py trace <existing trace CLI arguments>',
            'bridge': 'toolbox.py bridge <OpenOCD/J-Link bridge arguments>',
            'fixtures': 'toolbox.py fixtures rtt|scope --out NEW_DIR',
            'probe-flash': 'toolbox.py probe-flash [--image-dir BOOT_PACKAGE] [--dry-run|--verify-only|--backup-only] (direct JTAG, no browser/runtime)',
            'browserRequired': True, 'hardwareValidationReport': 'docs/F103ZE-Web-CLI-ETM统一验收-20261031.md',
            'completion': '事件投递不代表业务完成；读取状态/质量/日志验证。invoke等待原方法返回，原方法可能自行捕获错误。'}


class Client:
    def __init__(self, runtime, timeout=60):
        folder = Path(runtime).resolve()
        state = load_json(folder / 'toolbox-runtime.json')
        self.url = state['url']
        u = urlsplit(self.url)
        if u.scheme != 'http' or u.hostname != '127.0.0.1' or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
            raise ValueError('运行时URL必须为本机 http://127.0.0.1:端口')
        token = (folder / 'cli-token').read_text(encoding='ascii').strip()
        if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
            raise ValueError('无效CLI令牌')
        self.headers = {'X-Trace-CLI': token, 'Content-Type': 'application/json'}
        self.timeout = timeout

    def http(self, path, data=None):
        encoded = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
        if encoded is not None and len(encoded) > 47 << 20:
            raise ValueError('请求超过47 MiB；ETM大文件请使用 trace import-record/decode/export')
        try:
            with urlopen(Request(self.url + '/trace-cli/' + path, data=encoded, headers=self.headers), timeout=10) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError('队列HTTP %s: %s' % (error.code, error.read(4000).decode('utf-8', errors='replace'))) from error

    def result(self, jid):
        if len(jid) != 32 or any(c not in '0123456789abcdef' for c in jid):
            raise ValueError('无效job ID')
        return self.http('result/' + jid)

    def request(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('请求必须为JSON对象')
        try:
            jid = self.http('request', payload)['id']
        except OSError as error:
            raise RuntimeError('提交连接中断，是否已排队未知，禁止自动重试：' + str(error)) from error
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                value = self.result(jid)
            except Exception as error:
                raise RuntimeError('查询结果连接中断；操作可能仍在执行。使用 job %s 查询，不要重试原操作：%s' % (jid, error)) from error
            if value['state'] == 'done':
                result = value['result']
                # Keep completed jobs queryable for an hour; no auto-ack that could
                # destroy evidence if stdout fails or a caller loses its connection.
                return {'job': jid, **result}
            if time.monotonic() >= deadline:
                raise TimeoutError('等待结果超时，操作可能仍在执行。不要重复提交！使用 job %s 查询。' % jid)
            time.sleep(0.1)


def pack_file(path, relative=None):
    path = Path(path)
    if path.stat().st_size > 24 << 20:
        raise ValueError('单文件超过24 MiB；ETM大文件请使用 trace 接口')
    value = {'$base64': base64.b64encode(path.read_bytes()).decode('ascii'), 'name': path.name}
    if relative:
        value['relativePath'] = relative
    return value


def expand_arguments(value):
    """JSON file references, without shell interpolation or JavaScript evaluation."""
    if isinstance(value, list):
        return [expand_arguments(v) for v in value]
    if isinstance(value, dict):
        if '$file' in value:
            kind = value.get('kind', 'file')
            if kind not in ('file', 'buffer', 'bytes'):
                raise ValueError('$file kind只允许file/buffer/bytes')
            return {**pack_file(value['$file']), 'kind': kind}
        return {k: expand_arguments(v) for k, v in value.items()}
    return value


def serve(args):
    if not 1024 <= args.port <= 65535:
        raise ValueError('端口须为1024～65535')
    if bool(args.bit) != bool(args.zynq_elf):
        raise ValueError('--bit与--zynq-elf必须同时指定')
    # Reuse the existing full application, ETM API and authenticated loopback queue.
    sys.path.insert(0, str(ROOT / 'etm-service/tools'))
    spec = importlib.util.spec_from_file_location('toolbox_service', ROOT / 'web/tools/dev/serve-etm.py')
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    from waitress.server import create_server
    folder = Path(args.runtime).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    token = secrets.token_hex(32)
    (folder / 'cli-token').write_text(token, encoding='ascii')
    temporary = folder / 'tmp'
    temporary.mkdir()
    os.environ['TEMP'] = os.environ['TMP'] = str(temporary)
    pair = (args.bit, args.zynq_elf) if args.bit else None
    app = service.create_application(ROOT / 'etm-service', ROOT / 'web', folder / 'cli-token', pair, args.native_probe)
    # Keep HTTP/1.1 connections alive. Closing every byte-level USB RPC can
    # exhaust Windows' 16384 ephemeral TCP ports during debug pressure tests.
    server = create_server(app, host='127.0.0.1', port=args.port, threads=16,
                           connection_limit=64, max_request_body_size=48 << 20)
    state = {'protocol': 'workbench/1', 'url': 'http://127.0.0.1:' + str(args.port), 'pid': os.getpid(), 'status': 'serving'}
    state['nativeProbe']=bool(args.native_probe)
    from engine_profile import current_profile
    state['decodeEngineProfile']=current_profile()
    if pair:
        state['nativeCapture'] = {'bit': str(Path(args.bit).resolve()),
                                  'bitSha256': hashlib.sha256(Path(args.bit).read_bytes()).hexdigest(),
                                  'elf': str(Path(args.zynq_elf).resolve()),
                                  'elfSha256': hashlib.sha256(Path(args.zynq_elf).read_bytes()).hexdigest(),
                                  'note': '声明采集配对；服务不会加载板卡，请先通过JTAG加载相同文件'}
    emit(state, folder / 'toolbox-runtime.json')
    emit({**state, 'browserUrl': state['url'] + '/?trace-cli=' + token + '#flash',
          'note': ('已启用本地探针通路；在浏览器打开browserUrl并保持页面打开。Ctrl+C退出服务。'
                   if args.native_probe else '在Chrome/Edge打开browserUrl，保持页面打开；首次硬件授权需在网页完成。Ctrl+C退出服务。')})
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        server.task_dispatcher.shutdown()
        state['status'] = 'stopped'
        (folder / 'toolbox-runtime.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', help='serve创建的工作台运行时目录（不是trace native运行时）')
    p.add_argument('--timeout', type=float, default=60, help='等待结果秒数；超时不取消/不重试')
    p.add_argument('--out', help='JSON结果文件，拒绝覆盖')
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('catalog', help='离线列出全部页面分类和功能范围')
    c.add_argument('--full', action='store_true', help='输出总清单，包括静态控件、选项和方法源码位置')
    s = sub.add_parser('serve', help='启动本机工作台和CLI队列，前台运行')
    s.add_argument('--port', type=int, default=8878)
    s.add_argument('--bit', help='显式启用本地服务ETM采集：已加载的探针bit路径')
    s.add_argument('--zynq-elf', help='已加载的配套探针ELF；与--bit一起指定')
    s.add_argument('--native-probe', action='store_true', help='通过鉴权本机服务使用实际USB/HID/COM，复用网页协议与界面')
    sub.add_parser('ping', help='检查浏览器worker就绪，不访问设备')
    sub.add_parser('status', help='工作台摘要')
    s = sub.add_parser('job', help='查询超时/历史操作结果，不重试')
    s.add_argument('id')
    s = sub.add_parser('ack', help='删除已完成job结果，释放队列容量')
    s.add_argument('id')
    s = sub.add_parser('request', help='发送一条JSON请求文件，支持已有Trace浏览器动作')
    s.add_argument('file')
    s = sub.add_parser('batch', help='顺序执行JSON数组；首个失败停止，非事务')
    s.add_argument('file')
    s = sub.add_parser('page', help='按分类操作真实Web页面')
    s.add_argument('page', choices=list(PAGES))
    commands = s.add_subparsers(dest='op', required=True)
    for name in ('describe', 'state', 'show', 'downloads'):
        c = commands.add_parser(name)
        if name == 'describe':
            c.add_argument('--target', default='view', help='view/session等，以describe返回的targets为准')
    c = commands.add_parser('download', help='分块保存暂存的Blob导出；拒绝覆盖')
    c.add_argument('id')
    c.add_argument('destination')
    c = commands.add_parser('discard', help='释放浏览器暂存的导出')
    c.add_argument('id')
    c = commands.add_parser('event', help='键盘/鼠标/指针/滚轮事件（仍受浏览器用户手势限制）')
    c.add_argument('selector')
    c.add_argument('event', choices=['keydown', 'keyup', 'mousedown', 'mousemove', 'mouseup', 'pointerdown', 'pointermove', 'pointerup', 'wheel', 'dblclick', 'click', 'input', 'change'])
    c.add_argument('--data', default='{}', help='JSON事件参数；x/y为相对控件左上角的像素')
    for name in ('read', 'click', 'interrupt', 'set', 'upload', 'wait'):
        c = commands.add_parser(name)
        c.add_argument('selector', help='describe返回的CSS selector，必须唯一匹配')
        if name == 'set':
            c.add_argument('value', help='JSON值；字符串需用JSON引号，也可 --value-file')
            c.add_argument('--value-file', action='store_true', help='value视为JSON文件路径')
        elif name == 'upload':
            c.add_argument('files', nargs='+')
            c.add_argument('--directory', action='store_true', help='上传一个源码目录，保留相对路径')
        elif name == 'wait':
            condition = c.add_mutually_exclusive_group(required=True)
            condition.add_argument('--contains', help='等待控件文本包含内容；仍需检查业务质量')
            condition.add_argument('--enabled', action='store_true', help='等待控件恢复可用；用于同名文件再次上传后的异步完成检查')
    c = commands.add_parser('invoke', help='调用describe公开的原方法，等待其Promise返回')
    c.add_argument('method')
    c.add_argument('--target', default='view', help='以describe返回的targets为准')
    c.add_argument('--args', default='[]', help='JSON位置参数数组；大参数可用--args-file')
    c.add_argument('--args-file')
    sub.add_parser('trace', help='原样转交全部现有ETM Trace CLI参数（trace之后的--help）')
    sub.add_parser('bridge', help='启动可选OpenOCD/J-Link桥（bridge --help查看桥选项）')
    sub.add_parser('fixtures', help='构建F103ZE额定72MHz测试目标（fixtures --help查看参数）')
    sub.add_parser('probe-flash', help='备份并固化Zynq探针到QSPI（probe-flash --help查看参数）')
    v = sub.add_parser('validate', help='真实Web验收；scope/rttcdc会烧录目标，禁止Flash时用no-flash')
    v.add_argument('suite', choices=['capacity', 'debug', 'scope', 'rttcdc', 'no-flash'])
    v.add_argument('--artifacts', required=True, help='新的证据目录，拒绝覆盖')
    v.add_argument('--elf', default=str(ROOT / 'prebuilt/20261031_f103ze_cdc_trace/fw-48-echo.elf'))
    v.add_argument('--sources', default=str(ROOT / 'docs/validation/f103ze-web-flow-20261031/source-snapshot'))
    v.add_argument('--lengths', default='0.01,0.1,0.2,1')
    v.add_argument('--rounds', type=int, default=20)
    v.add_argument('--case-timeout', type=float, default=600)
    v.add_argument('--clocks',default='20000000,30000000,36000000,45000000,60000000')
    v.add_argument('--periods',default='100,20,10,5,2')
    v.add_argument('--stream-seconds',type=float,default=.5)
    v.add_argument('--scope-channels',type=int,choices=[1,8],default=1)
    v.add_argument('--skip-scope',action='store_true',help='no-flash套件显式跳过已登记的J-Scope连续切换问题；报告保留DEFERRED')
    v.add_argument('--observe-clock',action='store_true',help='通过PS JTAG无暂停读取实际FCLK/SWD divider')
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'probe-flash':
        return subprocess.call([sys.executable, '-X', 'utf8', str(ROOT / 'tools/probe_flash.py'), *argv[1:]])
    if argv and argv[0] == 'trace':
        return subprocess.call([sys.executable, '-X', 'utf8', str(ROOT / 'etm-service/trace.py'), *argv[1:]])
    if argv and argv[0] == 'fixtures':
        return subprocess.call([sys.executable, '-X', 'utf8', str(ROOT / 'tools/build_f103_fixtures.py'), *argv[1:]])
    if argv and argv[0] == 'bridge':
        node = shutil.which('node')
        if not node:
            emit({'ok': False, 'error': '本地桥需要Node.js 18+'})
            return 1
        return subprocess.call([node, str(ROOT / 'web/bridge/rtt-bridge.mjs'), *argv[1:]])
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.timeout <= 0:
            raise ValueError('timeout必须大于0')
        if args.out and Path(args.out).exists():
            raise FileExistsError('拒绝覆盖结果文件：' + args.out)
        if args.command == 'catalog':
            if args.full:
                from tools.toolbox_catalog import full_catalog
                value = full_catalog(ROOT, catalog())
            else:
                value = catalog()
            emit({'ok': True, 'value': value}, args.out)
            return 0
        if not args.runtime:
            p.error('此命令需要 --runtime 目录')
        if args.command == 'serve':
            serve(args)
            return 0
        if args.command == 'validate':
            if args.suite=='no-flash':
                from tools.f103_no_flash_web_acceptance import run
            elif args.suite in ('scope','rttcdc'):
                from tools.f103_stream_acceptance import run
            else:
                from tools.f103_web_acceptance import run
            emit(run(args), args.out)
            return 0
        client = Client(args.runtime, args.timeout)
        if args.command == 'job':
            result = {'ok': True, 'value': client.result(args.id)}
        elif args.command == 'ack':
            client.result(args.id)  # validate ID before composing an endpoint
            result = {'ok': True, 'value': client.http('ack/' + args.id, {})}
        elif args.command == 'batch':
            requests = load_json(args.file)
            if not isinstance(requests, list) or not 1 <= len(requests) <= 1000:
                raise ValueError('batch必须为1～1000条JSON对象数组')
            results = []
            # Validate all local files/arguments before the first hardware action.
            requests = [expand_arguments(v) for v in requests]
            if any(not isinstance(v, dict) for v in requests):
                raise ValueError('batch每项必须为请求对象')
            for request in requests:
                value = client.request(request)
                results.append(value)
                if not value.get('ok'):
                    break
                client.http('ack/' + value['job'], {})
            result = {'ok': all(v.get('ok') for v in results), 'results': results,
                      'completed': len(results), 'total': len(requests), 'transactional': False}
        else:
            payload = {'action': args.command}
            if args.command == 'request':
                payload = expand_arguments(load_json(args.file))
            elif args.command == 'page':
                payload = {'action': 'workbench', 'page': args.page, 'op': args.op}
                for name in ('target', 'selector', 'method'):
                    if hasattr(args, name):
                        payload[name] = getattr(args, name)
                if args.op == 'download':
                    destination = Path(args.destination).resolve()
                    if destination.exists():
                        raise FileExistsError('拒绝覆盖：' + str(destination))
                    partial = destination.with_name(destination.name + '.partial')
                    offset = 0
                    digest = hashlib.sha256()
                    with partial.open('xb') as stream:
                        while True:
                            chunk = client.request({**payload, 'id': args.id, 'offset': offset})
                            if not chunk.get('ok'):
                                raise RuntimeError(str(chunk))
                            v = chunk['value']
                            data = base64.b64decode(v['base64'], validate=True)
                            if v['offset'] != offset or offset + len(data) > v['total'] or (not data and offset < v['total']):
                                raise ValueError('下载区间无效')
                            stream.write(data)
                            digest.update(data)
                            offset += len(data)
                            client.http('ack/' + chunk['job'], {})
                            if offset == v['total']:
                                break
                    # rename on Windows refuses existing destination. Recheck also
                    # covers normal POSIX use; destination is always user-selected.
                    if destination.exists():
                        raise FileExistsError('目标文件已存在；保留.partial')
                    partial.rename(destination)
                    result = {'ok': True, 'value': {'path': str(destination), 'bytes': offset, 'sha256': digest.hexdigest()}}
                    emit(result, args.out)
                    return 0
                elif args.op == 'discard':
                    payload['id'] = args.id
                elif args.op == 'event':
                    payload['event'] = args.event
                    payload['options'] = json.loads(args.data)
                    if not isinstance(payload['options'], dict):
                        raise ValueError('event data必须为对象')
                elif args.op == 'set':
                    payload['value'] = load_json(args.value) if args.value_file else json.loads(args.value)
                elif args.op == 'invoke':
                    values = load_json(args.args_file) if args.args_file else json.loads(args.args)
                    if not isinstance(values, list):
                        raise ValueError('args必须为JSON数组')
                    payload['args'] = expand_arguments(values)
                elif args.op == 'upload':
                    if args.directory:
                        if len(args.files) != 1 or not Path(args.files[0]).is_dir():
                            raise ValueError('--directory需要一个目录')
                        directory = Path(args.files[0]).resolve()
                        files = sorted(f for f in directory.rglob('*') if f.is_file() and not f.is_symlink())
                        if len(files) > 10000 or sum(f.stat().st_size for f in files) > 32 << 20:
                            raise ValueError('目录超过10000文件或32 MiB；请选择精简源码目录')
                        payload['files'] = [pack_file(f, directory.name + '/' + f.relative_to(directory).as_posix()) for f in files]
                    else:
                        payload['files'] = [pack_file(f) for f in args.files]
                elif args.op == 'wait':
                    payload['op'] = 'read'
                    deadline = time.monotonic() + args.timeout
                    while True:
                        result = client.request(payload)
                        if not result.get('ok') or (args.enabled and result.get('value', {}).get('disabled') is False) or (not args.enabled and args.contains in result.get('value', {}).get('text', '')):
                            break
                        client.http('ack/' + result['job'], {})
                        if time.monotonic() >= deadline:
                            raise TimeoutError('等待控件文本超时；未自动停止硬件操作')
                        time.sleep(.25)
                    emit(result, args.out)
                    return 0 if result.get('ok') else 1
            result = client.request(payload)
        emit(result, args.out)
        return 0 if result.get('ok') else 1
    except Exception as error:
        emit({'ok': False, 'error': str(error), 'type': type(error).__name__})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
