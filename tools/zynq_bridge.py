"""Double-click Windows bridge: one local workbench, real Zynq LA, native decode.

No firmware download, PLL/AHB changes, or USB enumeration occurs at startup.
User captures and authentication state are outside the bundled application.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid
import webbrowser
from urllib.request import urlopen


VERSION = '1.0.0'
FROZEN = bool(getattr(sys, 'frozen', False))
REPO = Path(__file__).resolve().parents[1]


def locations():
    if FROZEN:
        runtime = Path(sys._MEIPASS)
        return Path(sys.executable).resolve().parent, runtime / 'backend', runtime / 'toolbox', runtime / 'serve-etm.py', runtime / 'hosttools'
    return REPO, REPO / 'etm-service', REPO / 'web', REPO / 'web/tools/dev/serve-etm.py', REPO / 'tools'


def load_service(path):
    spec = importlib.util.spec_from_file_location('zynq_bridge_service', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def application(backend, web, service_path, helpers, data, token_file, *, offline=False):
    for path in (helpers, backend / 'tools', backend / 'tools/la'):
        sys.path.insert(0, str(path))
    os.environ['WEB_ETM_RECORDS'] = str(data / 'records')
    from engine_profile import activate_native_profile
    activate_native_profile()
    service = load_service(service_path)
    # The normal Web button is the production capture path. It preserves the
    # firmware's RCC settings, releases USB, arms Zynq, and restores the target.
    app = service.create_application(backend, web, token_file, native_probe=True)
    import decode_trace
    decode_trace.ROOT = backend  # frozen modules' __file__ is not the asset root
    backend_app = app.mounts['/etm']
    if offline:
        from flask import abort, request
        @app.app.before_request
        def disable_native_io():
            if request.path.startswith('/native-probe/'):
                abort(403, description='离线验收：硬件访问已禁用')
        @backend_app.before_request
        def disable_capture_io():
            if request.path in ('/api/status', '/api/capture', '/api/native-capture'):
                abort(403, description='离线验收：硬件访问已禁用')
        for target in (app.app, backend_app):
            @target.after_request
            def offline_notice(response):
                if response.mimetype == 'text/html' and response.status_code == 200 and 'attachment' not in response.headers.get('Content-Disposition','').lower():
                    text=response.get_data(as_text=True)
                    response.set_data(text.replace('</body>', '<div role="status" style="position:fixed;bottom:0;right:0;z-index:99999;background:#663b00;color:white;padding:6px">离线验收：硬件访问已禁用</div></body>'))
                return response
    return app


def preflight(backend, web, service_path):
    required=[backend / 'server.py', service_path, web / 'index.html', backend / 'web/index.html',
              backend/'web/app/standalone-flame.js', backend/'web/app/standalone-flame.css']
    for path in required:
        if not path.is_file():
            raise ValueError('程序目录不完整，请保留完整程序目录：' + str(path))
    versions={}
    for name in ('etm_decode', 'etm_frontend', 'etm_storebuild', 'etm_index', 'etm_export', 'etm_framed'):
        executable=backend / 'build-native' / (name + '.exe')
        usage_only=name in ('etm_decode','etm_index')
        result=subprocess.run([str(executable)] + ([] if usage_only else ['--version']), capture_output=True, timeout=20)
        text=(result.stdout or result.stderr).decode('utf8', 'replace').strip()
        if result.returncode and not (usage_only and text.lower().startswith('usage: '+name)):
            raise ValueError('原生工具无法启动：' + name + ' ' + result.stderr.decode('utf8', 'replace'))
        versions[name]={'response':text,'sha256':hashlib.sha256(executable.read_bytes()).hexdigest()}
    import usb.core, libusb_package, hid, serial, capstone
    if libusb_package.get_libusb1_backend() is None:
        raise ValueError('桥包缺少libusb运行库')
    return {'ok':True, 'native':versions, 'clockPolicy':'target-firmware-owned', 'hardwareAccess':False,
            'flameHtml':{'selfContained':True,'interactive':True},'offlineTraceCli':True}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf8', errors='replace')
    home, backend, web, service_path, helpers = locations()
    arguments=list(sys.argv[1:] if argv is None else argv)
    if arguments[:1]==['--trace-cli']:
        commands={'export','query','verify','decode','import-record','record','elf'}
        if len(arguments)==1 or arguments[1] in ('-h','--help'):
            print('Offline Trace CLI: --trace-cli '+', '.join(sorted(commands)))
            print('Example: --trace-cli export --record RECORD --format flame-html --flame-mode timeline --from-seq START --to-seq END --out flame.html')
            return 0
        if arguments[1] not in commands:
            print('离线Trace CLI不支持该命令；仅允许 '+', '.join(sorted(commands)),file=sys.stderr)
            return 2
        for path in (helpers,backend/'tools',backend/'tools/la'):sys.path.insert(0,str(path))
        from engine_profile import activate_native_profile
        activate_native_profile()
        import decode_trace
        decode_trace.ROOT=backend
        from trace_cli import main as trace_main
        return trace_main(arguments[1:])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8882)
    parser.add_argument('--data-dir', type=Path, default=home / 'data')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check', action='store_true', help='离线检查运行库和C++工具；不访问硬件')
    parser.add_argument('--offline', action='store_true', help='离线验收：禁止USB/HID/串口和采集，仅浏览、导入和解码')
    parser.add_argument('--trace-cli',action='store_true',help='离线记录CLI：--trace-cli export/query/verify/...；无需启动Web服务')
    args=parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        raise ValueError('端口必须在1024～65535之间')
    data=args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    url='http://127.0.0.1:' + str(args.port)
    manifest=home / 'package-manifest.json'
    package_id=hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else 'source'
    state_path=data / 'bridge-state.json'
    if not args.check and state_path.is_file():
        try:
            state=json.loads(state_path.read_text(encoding='utf8'))
            with urlopen(url+'/etm-launcher.json', timeout=1) as response:
                existing=json.load(response)
            if (existing.get('bootId')==state.get('bootId') and existing.get('packageId')==package_id
                    and existing.get('dataDirectory')==str(data) and existing.get('offline')==args.offline):
                if not args.no_browser:webbrowser.open(state['browserUrl'])
                print('工作台已经运行：' + url + '/#etm', flush=True)
                return 0
        except (OSError, ValueError):pass
    folder=data / 'runtime' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    token_file=folder / 'cli-token'
    token=secrets.token_hex(32)
    token_file.write_text(token, encoding='ascii')
    temporary=folder / 'tmp'
    temporary.mkdir()
    os.environ['TEMP']=os.environ['TMP']=str(temporary)
    app=application(backend, web, service_path, helpers, data, token_file, offline=args.offline)
    proof=preflight(backend, web, service_path)
    if args.check:
        print(json.dumps(proof, ensure_ascii=False), flush=True)
        return 0
    from waitress.server import create_server
    from flask import jsonify
    boot=uuid.uuid4().hex
    app.app.view_functions['launcher_info']=lambda:jsonify(protocol=1, portable=FROZEN, version=VERSION,
        packageId=package_id, bootId=boot, dataDirectory=str(data), offline=args.offline,
        clockPolicy='target-firmware-owned')
    try:
        server=create_server(app, host='127.0.0.1', port=args.port, threads=16,
            connection_limit=64, max_request_body_size=48 << 20)
    except OSError as error:
        raise ValueError(f'端口{args.port}已被占用；请关闭原桥或选择其他端口，不会停止其它服务') from error
    browser_url=url+'/?trace-cli='+token+'#etm'
    state={'protocol':'workbench/1','url':url,'browserUrl':browser_url,'pid':os.getpid(),
        'status':'serving','bootId':boot,'nativeProbe':True,'offline':args.offline,'runtime':str(folder),
        'recordsDirectory':str(data/'records')}
    for path in (folder / 'toolbox-runtime.json', state_path):
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print('Zynq ETM 工作台 '+VERSION+'；时钟由target固件负责', flush=True)
    print('数据目录：'+str(data), flush=True)
    print('工作台：'+browser_url, flush=True)
    print('浏览器中载入ELF → 连接探针 → 选择函数 → 核对时钟 → 联动采集；关闭本窗口停止服务。', flush=True)
    if not args.no_browser:webbrowser.open(browser_url)
    try:server.run()
    except KeyboardInterrupt:pass
    finally:
        server.close()
        server.task_dispatcher.shutdown()
        state['status']='stopped'
        for path in (folder / 'toolbox-runtime.json', state_path):
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return 0


if __name__ == '__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print('启动失败：'+str(error), file=sys.stderr, flush=True)
        if FROZEN and len(sys.argv)==1:
            input('按回车关闭窗口…')
        raise SystemExit(1)
