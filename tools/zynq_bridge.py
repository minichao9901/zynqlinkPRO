"""Double-click Windows bridge: one local workbench, real Zynq LA, native decode.

No firmware download, PLL/AHB changes, or USB enumeration occurs at startup.
User captures and authentication state are outside the bundled application.
"""
import argparse
import base64
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
import threading
import time
from contextlib import contextmanager
from urllib.request import urlopen


VERSION = '1.0.0'
FROZEN = bool(getattr(sys, 'frozen', False))
REPO = Path(__file__).resolve().parents[1]
ORIGINAL_TEMP = {key: os.environ.get(key) for key in ('TEMP', 'TMP')}


def browser_environment():
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith('_PYI') or key in ('PYTHONHOME', 'PYTHONPATH'):
            environment.pop(key)
    for key, value in ORIGINAL_TEMP.items():
        if value is not None:
            environment[key] = value
    if FROZEN:
        runtime = Path(sys._MEIPASS).resolve()
        environment['PATH'] = os.pathsep.join(part for part in environment.get('PATH', '').split(os.pathsep)
            if part and not Path(part).resolve().is_relative_to(runtime))
    return environment


def browser_broker(executable, url):
    # A system process provides a fresh Windows loader context if Chromium
    # rejects the inherited frozen process state. Values are data, never code.
    command = ("$ErrorActionPreference='Stop'; $shell=New-Object -ComObject Shell.Application; "
        "$location=0; $root=$null; $handle=0; "
        "$desktop=$shell.Windows().FindWindowSW([ref]$location,[ref]$root,8,[ref]$handle,1); "
        "$desktop.Document.Application.ShellExecute($env:ZYNQ_BROWSER_EXE,$env:ZYNQ_BROWSER_URL,'','open',1)")
    environment = browser_environment()
    environment.update(ZYNQ_BROWSER_EXE=str(executable), ZYNQ_BROWSER_URL=url)
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    with system_dll_search():
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand',
            base64.b64encode(command.encode('utf-16le')).decode('ascii')],
            env=environment, cwd=os.environ['SystemRoot'], creationflags=subprocess.CREATE_NO_WINDOW,
            capture_output=True, timeout=10)
    if result.returncode:
        print('系统浏览器启动器返回错误：' + str(result.returncode), file=sys.stderr, flush=True)
    return result.returncode == 0


def windows_browsers():
    """Discover installed WebUSB-capable browsers without replaying shell flags."""
    import winreg
    for name in ('chrome.exe', 'msedge.exe'):
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, 'Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\' + name,
                                        0, winreg.KEY_READ | view) as key:
                        path = Path(os.path.expandvars(winreg.QueryValueEx(key, '')[0]).strip('"'))
                    if path.is_file():
                        yield path
                except OSError:
                    pass


@contextmanager
def system_dll_search():
    # PyInstaller's process-wide DLL directory is inherited by external apps.
    # Restore it immediately so our bundled native tools retain their libraries.
    if sys.platform != 'win32' or not FROZEN:
        yield
        return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    size = kernel.GetDllDirectoryW(0, None)
    buffer = ctypes.create_unicode_buffer(size + 1)
    kernel.GetDllDirectoryW(len(buffer), buffer)
    if not kernel.SetDllDirectoryW(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not kernel.SetDllDirectoryW(buffer.value or None):
            raise ctypes.WinError(ctypes.get_last_error())


def open_workbench(url):
    """Both fresh launch and reuse use the same external-browser launcher."""
    try:
        if sys.platform == 'win32':
            for executable in dict.fromkeys(windows_browsers()):
                try:
                    with system_dll_search():
                        child = subprocess.Popen([str(executable), '--new-window', url],
                            env=browser_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    try:
                        code = child.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        code = None
                    if code in (None, 0):
                        print('已调用浏览器：' + executable.name, flush=True)
                        return True
                    print(f'浏览器启动返回错误：{executable.name} ({code})', file=sys.stderr, flush=True)
                    if FROZEN and browser_broker(executable, url):
                        print('已调用浏览器（系统启动器）：' + executable.name, flush=True)
                        return True
                except OSError as error:
                    print('浏览器启动失败：' + executable.name + ' ' + str(error), file=sys.stderr, flush=True)
                    continue
        with system_dll_search():
            if webbrowser.open(url):
                return True
    except OSError as error:
        print('浏览器启动失败：' + str(error), file=sys.stderr, flush=True)
    print('未能自动打开浏览器，请手动打开上方工作台网址。', file=sys.stderr, flush=True)
    return False


def open_when_ready(base_url, browser_url, boot):
    # Binding a socket is not enough: Waitress must already be serving requests.
    for _ in range(100):
        try:
            with urlopen(base_url + '/etm-launcher.json', timeout=.5) as response:
                if json.load(response).get('bootId') == boot:
                    open_workbench(browser_url)
                    return
        except (OSError, ValueError):
            pass
        time.sleep(.1)
    print('服务启动等待超时，请手动打开上方工作台网址。', file=sys.stderr, flush=True)


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
                    text=text.replace('<body','<body data-native-offline="1"',1)
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
            'flameHtml':{'selfContained':True,'interactive':True,'tabs':['timeline','cycles'],'defaultTab':'timeline','dragSelectZoom':True},'offlineTraceCli':True}


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
                if not args.no_browser:open_workbench(state['browserUrl'])
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
    try:
        if args.no_browser:
            server.run()
        else:
            # Keep Windows browser activation and its lazy platform imports on
            # the main thread; serve HTTP concurrently before opening the page.
            worker = threading.Thread(target=server.run, daemon=True)
            worker.start()
            open_when_ready(url, browser_url, boot)
            while worker.is_alive():
                worker.join(.5)
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
