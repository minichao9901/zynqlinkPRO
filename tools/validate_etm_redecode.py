"""Offline main-to-candidate upgrades, mode switches and input mutation checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def worker(args):
    sys.path.insert(0, str(args.repo / 'etm-service/tools'))
    from trace_cli import engine_environment
    from decode_stream import decode_stream
    import trace_store as ts
    from trace_store_adapter import verify_inputs
    engine_environment()
    os.environ['ETM_DIRECT_DECODE'] = '0' if args.mode == 'binary' else '1'
    os.environ['ETM_BUFFERED_DECODE'] = '0' if args.mode == 'rescan' else '1'
    folder = args.dest
    folder.mkdir(parents=True, exist_ok=True)
    for name in ('firmware.elf', 'sources.json', 'session.json'):
        if not (folder / name).exists():
            shutil.copy2(args.record / name, folder / name)
    metadata = json.loads((args.record / 'decoded.json').read_text(encoding='utf8'))
    raw_path = args.record / 'etm.bin'
    if not raw_path.exists():
        raw_path = args.record / 'capture.bin'
    raw = raw_path.read_bytes()
    session = json.loads((folder / 'session.json').read_text(encoding='utf8'))
    relative = Path(session.get('input', 'capture.bin'))
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('unsafe record input path')
    if not (folder / relative).exists():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.record / relative, folder / relative)
    state = {}
    original_assemble = ts._BlockSink.assemble
    before = {name: sha(folder / name) for name in ('store/manifest.json', 'decoded.json') if (folder / name).exists()}

    def mutate_input():
        path = folder / ('native.bin' if args.fault == 'unused-native' else args.fault)
        data = path.read_bytes()
        stat = path.stat()
        state.update(path=path, data=data, stat=stat)
        changed = bytes([data[0] ^ 1]) + data[1:]
        path.write_bytes(changed)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        state['changedSha'] = sha(path)

    def mutate(sink, *positional, **keywords):
        result = original_assemble(sink, *positional, **keywords)
        mutate_input()
        return result

    try:
        with ExitStack() as stack:
            if args.fault:
                stack.enter_context(patch.object(ts._BlockSink, 'assemble', mutate))
                if (args.repo / 'etm-service/tools/native_complete.py').is_file():
                    import native_complete
                    original_publish = native_complete.publish
                    def mutate_complete(*positional, **keywords):
                        mutate_input()
                        return original_publish(*positional, **keywords)
                    stack.enter_context(patch.object(native_complete, 'publish', mutate_complete))
            decoded = decode_stream(raw, folder / 'firmware.elf', folder, metadata['config'],
                json.loads((folder / 'sources.json').read_text(encoding='utf8')),
                framing=metadata.get('framing'), physical=metadata.get('physical'), capture=metadata.get('capture'))
        manifest = json.loads((folder / 'store/manifest.json').read_text(encoding='utf8'))
        verification = verify_inputs(folder, manifest)
        assert verification['verified'] and not verification['problems'], verification
        return dict(ok=True, summary=decoded['summary'], quality=decoded['quality'],
                    sourceInput=manifest['bindings'].get('sourceInput'),
                    inputs=manifest['bindings']['inputs'], verification=verification,
                    hashSkipped=manifest['bindings'].get('inputHash', {}).get('skipped', False))
    except Exception as error:
        return dict(ok=False, errorType=type(error).__name__, error=str(error),
                    mutationApplied=bool(state), changedSha=state.get('changedSha'),
                    previousPublicationUnchanged=all(sha(folder / name) == digest for name, digest in before.items()))
    finally:
        if state:
            state['path'].write_bytes(state['data'])
            os.utime(state['path'], ns=(state['stat'].st_atime_ns, state['stat'].st_mtime_ns))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-root', type=Path)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--repo', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--dest', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--mode', choices=['binary', 'direct', 'rescan'], default='direct', help=argparse.SUPPRESS)
    parser.add_argument('--fault', default='', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.record = args.record.resolve()
    if args.worker:
        result = worker(args)
        save(args.out, result)
        return
    if not args.main_root:
        parser.error('--main-root is required')
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    folder = args.out / 'upgraded-record'
    rows = []
    source_before = {p.name: sha(p) for p in args.record.iterdir() if p.is_file() and p.name in ('etm.bin', 'capture.bin', 'firmware.elf')}

    def run(label, repo, mode, fault=''):
        output = args.out / (label + '.json')
        command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--worker',
                   '--repo', str(repo.resolve()), '--record', str(args.record), '--dest', str(folder),
                   '--out', str(output), '--mode', mode, '--fault', fault]
        result = subprocess.run(command, capture_output=True, timeout=180)
        assert result.returncode == 0, result.stderr.decode('utf8', 'replace')
        value = json.loads(output.read_text(encoding='utf8'))
        rows.append(dict(case=label, ok=value['ok'], fault=fault, mode=mode))
        return value

    baseline = run('main-created', args.main_root, 'binary')
    assert baseline['ok'], baseline
    native_before = sha(folder / 'native.bin')
    assert native_before != sha(folder / 'etm.bin')
    shutil.copytree(folder, args.out / 'main-record')
    expected = args.out / 'main-store'
    shutil.copytree(folder / 'store', expected)
    sys.path.insert(0, str(ROOT / 'tools'))
    from compare_etm_stores import compare
    comparisons = {}
    for label, mode in [('upgrade-direct', 'direct'), ('switch-binary', 'binary'), ('switch-rescan', 'rescan'), ('repeat-direct', 'direct')]:
        result = run(label, ROOT, mode)
        assert result['ok'], result
        assert result['summary'] == baseline['summary'] and result['quality'] == baseline['quality']
        assert not result['hashSkipped']
        assert sha(folder / 'native.bin') == native_before
        source = result['sourceInput']
        assert source['sha256'] == sha(folder / ('native.bin' if mode == 'binary' else 'etm.bin'))
        if mode == 'binary':
            assert result['inputs']['native.bin']['sha256'] == native_before
        else:
            assert 'native.bin' not in result['inputs'] and 'native.bin' in result['verification']['excluded']
        comparisons[label] = compare(expected, folder / 'store')
    for mode, fault in [('direct', 'etm.bin'), ('direct', 'firmware.elf'), ('direct', 'native-config.txt'),
                        ('direct', 'image-0.bin'), ('binary', 'native.bin')]:
        result = run('changed-' + fault.replace('.', '-'), ROOT, mode, fault)
        assert not result['ok'] and result['mutationApplied'] and result['previousPublicationUnchanged'], result
        assert '变化' in result['error'] or 'changed' in result['error'], result
    unused = run('unused-native-mutation', ROOT, 'direct', 'unused-native')
    assert unused['ok'] and 'native.bin' in unused['verification']['excluded'], unused
    comparisons['unused-native-mutation'] = compare(expected, folder / 'store')
    assert sha(folder / 'native.bin') == native_before
    assert all(sha(args.record / name) == digest for name, digest in source_before.items())
    save(args.out / 'result.json', dict(ok=True, rows=rows, comparisons=comparisons,
         originalNativePreserved=True, sourceRecordUnchanged=True, inputMutationRejected=5))
    print('Main upgrade, binary/direct/rescan switches, 5 true input mutations, unused native preservation: PASS')


if __name__ == '__main__':
    main()
