#!/usr/bin/env python3
"""Zynq ETM CLI for this repository.

`capture` and `doctor` are Zynq-native. Offline commands (`decode`, `query`,
`verify`, `export`, `record`, `elf`) delegate to the retained superlinkPRO
trace CLI in `tools/trace_cli.py`, so their JSON schema and rules stay the same.

Usage:
  python -X utf8 etm-service/trace.py doctor
  python -X utf8 etm-service/trace.py capture --elf ... --out ... --seconds 0.01
  python -X utf8 etm-service/trace.py query --record ... --view summary
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

SERVICE = Path(__file__).resolve().parent
REPO = SERVICE.parent
TOOLS = SERVICE / 'tools'
CLI = TOOLS / 'trace_cli.py'
BOARD = REPO / 'tools' / 'test_orbtrace_board.py'
DEFAULT_TARGET_ELF = SERVICE / 'firmware' / 'stm32f103_cdc_trace' / 'fw-ze.elf'
DEFAULT_BIT = REPO / 'prebuilt' / '20261030_orbtrace_oversample_parser' / 'orbtrace_oversample_parser.bit'
DEFAULT_ZYNQ_ELF = REPO / 'prebuilt' / '20261030_orbtrace_oversample_parser' / 'zynqdap_orbtrace.elf'
PROTOCOL = 'trace-cli/1'


def envelope(command, ok, result=None, error=None, code=0, started=None):
    value = {'protocol': PROTOCOL, 'runId': time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8],
             'command': command, 'ok': ok, 'exitCode': code,
             'elapsedSeconds': round(time.perf_counter() - started, 3) if started else 0}
    if result is not None:
        value['result'] = result
    if not ok:
        value['error'] = error or {'type': 'CliError', 'message': 'unknown error'}
    return value


def fail(command, message, code=2, started=None, details=None):
    error = {'type': 'CliError', 'message': message}
    if details is not None:
        error['details'] = details
    print(json.dumps(envelope(command, False, error=error, code=code, started=started), ensure_ascii=False))
    return code


def long_temp():
    """etm_storebuild cannot create files under the 8.3 ADMINI~1 temp path."""
    folder = REPO / 'build' / 'tmp-long'
    folder.mkdir(parents=True, exist_ok=True)
    os.environ['TEMP'] = str(folder)
    os.environ['TMP'] = str(folder)
    return folder


def zynq_status():
    """Enumeration-only probe check; never claims the interface."""
    try:
        import libusb_package
        import usb.core
        device = usb.core.find(idVendor=0x0D28, idProduct=0x0204,
                               backend=libusb_package.get_libusb1_backend())
        if device is None:
            return {'ok': False, 'ready': False, 'message': '未找到 ZynqDAP（0d28:0204）'}
        endpoints = []
        for cfg in device:
            for intf in cfg:
                endpoints.extend(ep.bEndpointAddress for ep in intf)
        if 0x82 not in endpoints:
            return {'ok': False, 'ready': False, 'message': '当前探针没有 ETM bulk-in 0x82（可能是 akaLinkPro）'}
        return {'ok': True, 'ready': True, 'message': 'ZynqDAP 已连接，ETM bulk-in 0x82 存在'}
    except Exception as error:
        return {'ready': False, 'message': str(error)}


def doctor():
    started = time.perf_counter()
    checks = {}
    try:
        import usb.core  # noqa: F401
        import elftools  # noqa: F401
        import capstone  # noqa: F401
        checks['python'] = {'ok': True, 'version': sys.version.split()[0]}
    except Exception as error:
        checks['python'] = {'ok': False, 'error': str(error)}
    exes = ['etm_decode.exe', 'etm_export.exe', 'etm_frontend.exe', 'etm_index.exe', 'etm_storebuild.exe']
    checks['native'] = {'ok': all((SERVICE / 'build-native' / n).is_file() for n in exes),
                        'files': {n: (SERVICE / 'build-native' / n).is_file() for n in exes}}
    checks['zynq'] = zynq_status()
    try:
        import urllib.request
        with urllib.request.urlopen('http://127.0.0.1:8766/api/health', timeout=2) as response:
            checks['service'] = {'ok': response.status == 200,
                                 'health': json.loads(response.read().decode('utf-8'))}
    except Exception as error:
        checks['service'] = {'ok': False, 'error': str(error)}
    checks['target_elf'] = {'ok': DEFAULT_TARGET_ELF.is_file(), 'path': str(DEFAULT_TARGET_ELF)}
    checks['bit'] = {'ok': DEFAULT_BIT.is_file(), 'path': str(DEFAULT_BIT)}
    ok = all(item.get('ok') for item in checks.values())
    payload = envelope('doctor', ok, {'checks': checks}, code=0 if ok else 3, started=started)
    if not ok:
        payload['error'] = {'type': 'CliError', 'message': '依赖/服务未就绪', 'details': checks}
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if ok else 3


def capture(argv):
    started = time.perf_counter()
    import argparse
    parser = argparse.ArgumentParser(prog='trace.py capture', description='Zynq FPGA ETM capture + native decode')
    parser.add_argument('--elf', required=True, help='目标 ELF（必须与 Flash 匹配）')
    parser.add_argument('--out', required=True, help='新记录目录（必须不存在）')
    parser.add_argument('--seconds', type=float, default=0.05, help='采集时长 0..1 s，默认50 ms')
    parser.add_argument('--trace-id', type=int, default=2)
    parser.add_argument('--hclk-div', type=int, choices=(1, 2, 4), default=4,
                        help='临时 AHB 分频；默认4，实际TRACECLK取决于目标原始RCC配置')
    parser.add_argument('--swd-khz', type=int, default=1000, help='目标控制SWD时钟，默认1000 kHz')
    parser.add_argument('--entry', help='采集起点函数名或0x地址')
    parser.add_argument('--reset-to-entry', action='store_true')
    parser.add_argument('--entry-timeout', type=float, default=5)
    parser.add_argument('--usb-reconnect', action='store_true')
    parser.add_argument('--ready-file')
    parser.add_argument('--gpio-speed', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--bit', default=str(DEFAULT_BIT))
    parser.add_argument('--zynq-elf', default=str(DEFAULT_ZYNQ_ELF))
    parser.add_argument('--no-decode', action='store_true')
    parser.add_argument('--json-out')
    args = parser.parse_args(argv)

    if not 0 < args.seconds <= 1:
        return fail('capture', '采集时长必须为 0..1 s', 2, started)
    if not 1 <= args.trace_id <= 111:
        return fail('capture', 'Trace ID必须为1..111', 2, started)
    if not 1 <= args.swd_khz <= 50000:
        return fail('capture', 'SWD时钟必须为1..50000 kHz', 2, started)
    if args.json_out and Path(args.json_out).exists():
        return fail('capture', 'JSON输出已存在，拒绝覆盖：' + args.json_out, 2, started)
    out = Path(args.out).resolve()
    if out.exists():
        return fail('capture', '输出目录已存在，拒绝覆盖：%s' % out, 2, started)
    for name, path in [('目标ELF', args.elf), ('探针bit', args.bit), ('探针ELF', args.zynq_elf)]:
        if not Path(path).is_file():
            return fail('capture', '%s不存在：%s' % (name, path), 2, started)
    if not 0 < args.entry_timeout <= 30 or args.reset_to_entry and args.entry is None:
        return fail('capture', '起点等待必须为0..30秒；reset-to-entry必须指定entry', 2, started)
    if args.usb_reconnect and not args.reset_to_entry:
        return fail('capture', 'usb-reconnect需要reset-to-entry', 2, started)
    if args.ready_file and Path(args.ready_file).exists():
        return fail('capture', 'ready-file已存在', 2, started)
    if args.entry is not None:
        sys.path.insert(0, str(REPO / 'tools'))
        from f103_capture_entry import resolve_entry
        try:
            resolve_entry(args.elf, args.entry)
        except (ValueError, OSError) as error:
            return fail('capture', str(error), 2, started)
    status = zynq_status()
    if not status['ready']:
        return fail('capture', 'Zynq ETM 接收端未就绪：' + status['message'], 4, started, status)
    out.mkdir(parents=True)
    command = [sys.executable, str(BOARD),
               '--target-elf', str(Path(args.elf).resolve()),
               '--bit', str(Path(args.bit).resolve()),
               '--elf', str(Path(args.zynq_elf).resolve()),
               '--output', str(out),
               '--milliseconds', str(args.seconds * 1000),
               '--trace-id', str(args.trace_id),
               '--speed-khz', str(args.swd_khz),
               '--hclk-div', str(args.hclk_div),
               '--gpio-speed', str(args.gpio_speed)]
    if args.entry is not None:
        command += ['--entry', args.entry, '--entry-timeout', str(args.entry_timeout)]
        if args.reset_to_entry:
            command.append('--reset-to-entry')
        if args.usb_reconnect:
            command.append('--usb-reconnect')
    if args.ready_file:
        command += ['--ready-file', args.ready_file]
    completed = subprocess.run(command, cwd=str(REPO), text=True, capture_output=True)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or '').strip()[-1200:]
        return fail('capture', '上板采集失败', 4, started, {'command': command, 'output': detail})
    acceptance = json.loads((out / 'acceptance.json').read_text(encoding='utf-8'))
    etm = (out / 'etm.bin').read_bytes()
    if not etm:
        return fail('capture', '采集没有 source ID %d 的 ETM 字节' % args.trace_id, 5, started,
                    {'quality': acceptance.get('quality')})
    config = acceptance.get('config') or {}
    config['traceid'] = args.trace_id
    shutil.copy2(args.elf, out / 'firmware.elf')
    (out / 'capture.bin').write_bytes(etm)
    metadata = {
        'name': '%s · CLI %s' % (config.get('protocol', 'ETM'), time.strftime('%Y-%m-%d %H:%M:%S')),
        'created': time.time(), 'input': 'capture.bin', 'seconds': args.seconds,
        'config': config, 'quality': acceptance.get('quality'), 'rawFormat': 'bin',
        'targetVerified': True, 'captureScope': 'cli-entry-window' if args.entry else 'cli-continuous-window',
        'captureEntry': (acceptance.get('entry') or {}).get('address'),
        'captureExtent': {'requestedSeconds': args.seconds, 'actualSeconds': acceptance.get('capture_host_seconds'),
                          'complete': True, 'known': 'capture_host_seconds' in acceptance,
                          'basis': 'host monotonic ETM active window; not cycle-accurate timing'},
        'targetSnapshot': {'name': 'STM32F103ZE', 'hclkDiv': args.hclk_div,
                           'gpioSpeed': args.gpio_speed},
        'etmBytes': len(etm), 'etmSha256': acceptance.get('etm_sha256'),
    }
    (out / 'session.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Keep the board runner's actual target-before.json register snapshot intact.
    summary = None
    decode_error = None
    if not args.no_decode:
        long_temp()
        sys.path.insert(0, str(TOOLS))
        from decode_stream import decode_stream
        try:
            decoded = decode_stream(etm, out / 'firmware.elf', out, config)
            summary = decoded.get('summary')
        except Exception as error:
            decode_error = str(error)
    result = {'record': str(out), 'etmBytes': len(etm), 'etmSha256': metadata['etmSha256'],
              'quality': acceptance.get('quality'), 'summary': summary,
              'config': config, 'captureSeconds': args.seconds,
              'hclkDiv': args.hclk_div, 'gpioSpeed': args.gpio_speed}
    if decode_error:
        result['decodeError'] = decode_error
        payload = envelope('capture', False, result, started=started, code=5,
                           error={'type': 'DecodeError', 'message': decode_error,
                                  'details': {'record': str(out), 'etmBytes': len(etm)}})
    else:
        payload = envelope('capture', True, result, started=started)
    text = json.dumps(payload, ensure_ascii=False)
    print(text)
    if args.json_out:
        with Path(args.json_out).open('x', encoding='utf-8') as stream:
            stream.write(text + '\n')
    return 0 if not decode_error else 5


def delegate(argv):
    long_temp()
    return subprocess.call([sys.executable, '-X', 'utf8', str(TOOLS / 'cli_entry.py'), *argv])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        print('命令：doctor | capture | sweep | samples | decode | query | verify | export | record | elf | import-record')
        return 0
    command = argv[0]
    if command == 'doctor':
        return doctor()
    if command == 'capture':
        return capture(argv[1:])
    if command in ('samples', 'sweep'):
        script = REPO / 'tools' / ('trace_signal_analysis.py' if command == 'samples' else 'f103_trace_sweep.py')
        return subprocess.call([sys.executable, '-X', 'utf8', str(script), *argv[1:]])
    # Everything offline keeps the superlinkPRO CLI contract.
    return delegate(argv)


if __name__ == '__main__':
    sys.exit(main())
