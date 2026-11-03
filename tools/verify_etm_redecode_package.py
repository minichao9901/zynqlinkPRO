"""Verify a frozen offline Web upgrade of a main-produced record with native.bin."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--legacy-record', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    package, legacy, output = args.package.resolve(), args.legacy_record.resolve(), args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sid = 'record-legacy-native-upgrade'
    folder = output / 'data/records' / sid
    shutil.copytree(legacy, folder)
    expected = json.loads((folder / 'decoded.json').read_text(encoding='utf8'))
    original_native = sha(folder / 'native.bin')
    previous_manifest = sha(folder / 'store/manifest.json')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if key not in ('PYTHONHOME', 'PYTHONPATH')}
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    log = (output / 'server.log').open('w', encoding='utf8')
    process = subprocess.Popen([str(package / 'zynq-etm-bridge.exe'), '--offline', '--no-browser',
        '--data-dir', str(output / 'data'), '--port', str(port)], env=env,
        stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def request(path, body=None):
        data = json.dumps(body).encode('utf8') if body is not None else None
        with urlopen(Request('http://127.0.0.1:%d%s' % (port, path), data=data,
                             headers={'Content-Type': 'application/json'}), timeout=30) as response:
            return json.load(response)

    report = dict(ok=False, hardwareAccess=False, pythonOnPath=False, nodeOnPath=False)
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                health = request('/etm/api/health')
                break
            except OSError:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Frozen offline startup failed; inspect local server.log')
                time.sleep(.1)
        state = json.loads((output / 'data/bridge-state.json').read_text(encoding='utf8'))
        launcher = request('/etm-launcher.json')
        assert state['pid'] == process.pid and launcher['bootId'] == state['bootId']
        assert launcher['offline'] and launcher['dataDirectory'] == str((output / 'data').resolve())
        assert launcher['packageId'] == sha(package / 'package-manifest.json')
        assert health['decodeEngineProfile']['name'] == 'native'
        job = request('/etm/api/decode/' + sid, {})['job']
        deadline = time.monotonic() + 120
        while True:
            status = request('/etm/api/jobs/' + job)
            if status['state'] in ('done', 'error'):
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Frozen record upgrade timed out')
            time.sleep(.05)
        assert status['state'] == 'done', status
        overview = request('/etm/api/browse/' + sid + '/overview')
        assert overview['summary'] == expected['summary']
        assert sha(folder / 'native.bin') == original_native
        assert sha(folder / 'store/manifest.json') != previous_manifest
        manifest = json.loads((folder / 'store/manifest.json').read_text(encoding='utf8'))
        assert 'native.bin' not in manifest['bindings']['inputs']
        assert manifest['bindings']['sourceInput']['sha256'] == sha(folder / 'etm.bin')
        report.update(oldNativePreserved=True, newGenerationPublished=True, sourceInput=manifest['bindings']['sourceInput'])
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
    sys.path.insert(0, str(ROOT / 'tools'))
    from compare_etm_stores import compare
    report['comparison'] = compare(legacy / 'store', folder / 'store')
    report.update(ok=True, serverExited=True, packageManifestSha256=sha(package / 'package-manifest.json'))
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Frozen Web redecode of main record: PASS; old native preserved, full store equivalent')


if __name__ == '__main__':
    main()
