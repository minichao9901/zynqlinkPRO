"""Run the first-use manual's fixed CLI commands from the local workbench."""

from dataclasses import dataclass
import hmac
import json
from pathlib import Path
import re
import shlex
import subprocess
import threading
import uuid

from flask import abort, jsonify, request


MANUAL = 'docs/toolbox-cli-first-run.md'
WEB = 'python -X utf8 toolbox.py --runtime build/first-run-web '
TARGET = 'target-flash --chip stm32h7 --swd-khz 10000 --file "$Firmware"'


@dataclass(frozen=True)
class Command:
    name: str
    line: str
    hardware: bool = False
    confirmation: str = ''
    field: str = ''


COMMANDS = {item.line: item for item in (
    Command('workspace', "Set-Location 'E:/zynqlinkPRO'"),
    Command('python', 'python --version'),
    Command('install', 'python -m pip install -r etm-service/requirements.txt pefile'),
    Command('dependencies', 'python -X utf8 tools/verify_dependencies.py'),
    Command('ram-plan', 'python -X utf8 toolbox.py probe-load --dry-run'),
    Command('ram-check', 'python -X utf8 toolbox.py probe-load --check-only --out build/first-run-probe-check', True),
    Command('ram-load', 'python -X utf8 toolbox.py probe-load --out build/first-run-probe-load', True,
            '复位 Zynq 探针并临时加载正式 J7 bit 和 PS ELF。'),
    Command('workbench', WEB + 'serve --j7 --port 0 --open-browser'),
    Command('ping', WEB + 'ping'),
    Command('firmware', "$Firmware = Read-Host '输入 H743 固件 ELF 的绝对路径'", field='firmware'),
    Command('prepare', WEB + TARGET + ' --prepare-only', field='firmware'),
    Command('identity', WEB + 'page flash invoke readIdcode', True),
    Command('program', WEB + '--timeout 240 ' + TARGET, True,
            '擦写 STM32H743 目标 Flash，读回校验并复位。', 'firmware'),
    Command('flash-result', WEB + "page flash read '#f-result'"),
    Command('flash-log', WEB + "page flash read '#f-log'"),
    Command('job', WEB + 'job JOB_ID', field='job'),
    Command('qspi-check', 'python -X utf8 toolbox.py probe-load --check-only --out build/first-run-qspi-check', True),
    Command('qspi-plan', 'python -X utf8 toolbox.py probe-flash --dry-run'),
    Command('qspi-write', 'python -X utf8 toolbox.py probe-flash --out build/first-run-qspi-program', True,
            '备份并写入 Zynq 探针本体的 QSPI，随后复位验证。'),
    Command('qspi-cold', 'python -X utf8 toolbox.py project run probe.ocm-verify -- '
            '--elf prebuilt/release-20261106/application.elf --require-qspi --out-dir build/first-run-qspi-cold', True),
)}
BY_NAME = {item.name: item for item in COMMANDS.values()}
FENCE = re.compile(r'^   ```powershell\n([^\n]+)\n   ```$', re.M)


def read_manual(workspace, offline):
    source = (workspace / MANUAL).read_text(encoding='utf8').strip()
    rows = []
    start = 0
    for match in FENCE.finditer(source):
        rows.append({'text': source[start:match.start()].strip()})
        line = match[1].strip()
        command = COMMANDS.get(line)
        if command is None:
            raise ValueError(f'手册命令尚未绑定执行操作：{line}')
        rows.append({'id': command.name, 'line': line, 'field': command.field,
                     'confirmation': command.confirmation, 'disabled': offline and command.hardware})
        start = match.end()
    if not rows or source.count('```powershell') * 2 != source.count('```'):
        raise ValueError('入门手册的命令块格式有误')
    rows.append({'text': source[start:].strip()})
    return rows


def firmware_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or path.suffix.lower() != '.elf' or not path.is_file():
        raise ValueError('请输入本机已有的 ELF 文件的绝对路径')
    return str(path.resolve())


def start_command(command, value, workspace, runtime, folder, python, output):
    if command.field == 'firmware':
        value = firmware_path(value)
    elif command.field == 'job' and not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('请输入 32 位十六进制的 CLI job ID')
    if command.name == 'workspace':
        output.write(f'工作目录：{workspace}\n'.encode('utf8'))
        return None
    if command.name == 'workbench':
        state = json.loads((runtime / 'toolbox-runtime.json').read_text(encoding='utf8'))
        if state.get('status') != 'serving' or not state.get('nativeProbe'):
            raise ValueError('请以本机探针模式启动工作台，再打开可执行手册。')
        output.write(json.dumps({
            'ready': True, 'url': state['url'], 'runtime': str(runtime), 'nativeProbe': True,
        }, indent=2).encode('utf8'))
        return None
    if command.name == 'firmware':
        output.write(f'已选择固件：{value}\n'.encode('utf8'))
        return None
    if not python:
        raise ValueError('未找到系统 Python。安装后重新启动本机工作台。')
    substitutions = {'build/first-run-web': str(runtime), '$Firmware': value, 'JOB_ID': value}
    args = shlex.split(command.line)[1:]
    if '--out' in args:
        substitutions[args[args.index('--out') + 1]] = str(folder / 'artifacts')
    args = [substitutions.get(argument, argument) for argument in args]
    output.write((subprocess.list2cmdline(['python', *args]) + '\n\n').encode('utf8'))
    output.flush()
    return subprocess.Popen([python, '-u', *args], cwd=workspace, stdin=subprocess.DEVNULL,
                            stdout=output, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def install(app, token_file, workspace, python, *, offline=False):
    """Install only on the authenticated, loopback workbench origin."""
    app.config['COMMAND_MANUAL'] = True
    token = token_file.read_bytes().strip()
    runtime = token_file.parent.resolve()
    jobs = {}
    lock = threading.Lock()

    def authorize():
        supplied = request.headers.get('X-Trace-CLI', '').encode('utf8')
        if not hmac.compare_digest(token, supplied):
            abort(403)
        if request.method == 'POST' and request.headers.get('Origin') != request.host_url.rstrip('/'):
            abort(403)

    @app.get('/command-manual')
    def command_manual():
        authorize()
        if workspace is None:
            return jsonify(error='请用 --workspace 指定含入门手册的 ZynqLinkPRO 仓库目录。'), 409
        try:
            return jsonify(rows=read_manual(workspace, offline))
        except (OSError, ValueError) as error:
            return jsonify(error=str(error)), 409

    @app.post('/command-manual/run')
    def run_manual_command():
        authorize()
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get('id'), str):
            abort(400)
        command = BY_NAME.get(body['id'])
        if command is None or workspace is None:
            abort(404)
        if offline and command.hardware:
            return jsonify(error='离线模式已禁用硬件命令。'), 403
        if command.confirmation and body.get('confirmed') is not True:
            return jsonify(error='请确认此操作。'), 400
        value = body.get('value', '')
        if not isinstance(value, str) or len(value) > 4096:
            abort(400)
        with lock:
            if any(process is not None and process.poll() is None for process, _, _ in jobs.values()):
                return jsonify(error='手册中已有命令在运行，请等它结束。'), 409
            job = uuid.uuid4().hex
            folder = runtime / 'manual' / job
            folder.mkdir(parents=True)
            log = folder / 'output.log'
            exit_code = 0
            with log.open('wb') as output:
                try:
                    process = start_command(command, value.strip(), workspace, runtime, folder, python, output)
                except (OSError, ValueError, KeyError) as error:
                    output.write(f'{error}\n'.encode('utf8'))
                    process = None
                    exit_code = 1
            if len(jobs) >= 64:
                del jobs[next(iter(jobs))]
            jobs[job] = process, exit_code, log
        return jsonify(job=job)

    @app.get('/command-manual/job/<job>')
    def manual_job(job):
        authorize()
        entry = jobs.get(job)
        if entry is None:
            abort(404)
        process, exit_code, log = entry
        if process is not None:
            exit_code = process.poll()
        with log.open('rb') as output:
            size = output.seek(0, 2)
            offset = max(0, size - 96 * 1024)
            output.seek(offset)
            text = output.read(96 * 1024).decode('utf8', errors='replace')
        return jsonify(exitCode=exit_code, output=text, truncated=bool(offset), log=str(log))
