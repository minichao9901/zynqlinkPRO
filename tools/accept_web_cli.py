"""Exercise the shipped CLI against a real, already-open Web worker.

No target is opened/programmed and no hardware success is inferred. This
checks all eight page inventories and actual file inputs.
Hardware acceptance must be recorded separately after browser authorization.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from toolbox import PAGES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--out', type=Path, required=True, help='New evidence directory')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    results = []

    def cli(*command, ok=True):
        p = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'toolbox.py'),
                            '--runtime', args.runtime, '--timeout', '30', *command],
                           cwd=ROOT, text=True, encoding='utf-8', capture_output=True, timeout=45)
        try:
            value = json.loads(p.stdout)
        except ValueError as exc:
            raise RuntimeError(f'Invalid CLI JSON: {p.stdout}\n{p.stderr}') from exc
        results.append({'command': list(command), 'exitCode': p.returncode, 'result': value})
        (args.out / 'results.json').write_text(json.dumps({'hardwareValidated': False, 'results': results},
                                                       ensure_ascii=False, indent=2), encoding='utf-8')
        if (p.returncode == 0) != ok or bool(value.get('ok')) != ok:
            raise RuntimeError(f'Unexpected CLI result for {command}: {value}')
        return value.get('value')

    cli('ping')
    for page in PAGES:
        desc = cli('page', page, 'describe')
        if not desc['controls']:
            raise RuntimeError(f'No controls discovered for {page}')
        state = cli('page', page, 'state')
        if state['errors']:
            raise RuntimeError(f'Browser errors: {state["errors"]}')
        cli('page', page, 'show')
        control = next((c for c in desc['controls'] if not c['selector'].startswith('@file:')), None)
        cli('page', page, 'read', control['selector'])
    cli('page', 'etm', 'describe', '--target', 'history')
    cli('page', 'etm', 'describe', '--target', 'target')
    cli('page', 'dbg', 'invoke', 'summary')
    cli('page', 'dbg', 'invoke', '__proto__', ok=False)
    cli('page', 'dbg', 'read', 'button', ok=False)
    cli('page', 'dbg', 'interrupt', '#btn-probe-connect', ok=False)
    cli('page', 'etm', 'upload', '#elf-file', str(ROOT / 'prebuilt/golden/f103ze-cdc48.elf'))
    cli('page', 'etm', 'wait', '#elf-label', '--contains', 'f103ze-cdc48.elf')
    batch = args.out / 'requests.json'
    batch.write_text(json.dumps([{'action': 'workbench', 'page': 'serial', 'op': 'state'},
                                  {'action': 'workbench', 'page': 'etm', 'op': 'read', 'selector': '#job-state'}]))
    cli('batch', str(batch))
    single = args.out / 'request.json'
    single.write_text(json.dumps({'action': 'ping'}))
    cli('request', str(single))
    jid = results[-1]['result']['job']
    cli('job', jid)
    cli('ack', jid)
    summary = {'ok': True, 'hardwareValidated': False, 'pages': len(PAGES), 'commands': len(results)}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
