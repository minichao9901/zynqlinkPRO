"""Verify vendored build/simulation inputs without a toolchain, USB or network."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def verify(root, check_tracked=False):
    root = root.resolve()
    manifest = json.loads((root / 'docs/required-dependencies.json').read_text(encoding='utf-8'))
    failures = []
    checked = 0
    tracked = None
    if check_tracked:
        try:
            tracked = set(subprocess.check_output(
                ['git', 'ls-files', '-z'], cwd=root).decode('utf8').split('\0'))
        except (OSError, subprocess.CalledProcessError) as error:
            failures.append('Cannot verify dependency Git tracking: ' + str(error))
    for component in manifest['components']:
        for relative, expected in component['files'].items():
            if tracked is not None and relative not in tracked:
                failures.append(f'untracked input: {relative}')
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                failures.append(f'missing input: {relative}')
                continue
            checked += 1
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                failures.append(f'SHA-256 mismatch: {relative}')
    bsp = next(c for c in manifest['components'] if c['id'] == 'zynq-ps-bsp')
    library = bsp['library']
    for release in ('golden', 'recovery'):
        accepted = json.loads((root / f'prebuilt/{release}/firmware_build_60.json').read_text(encoding='utf-8'))
        if bsp['files'][library] != accepted['bsp_sha256']:
            failures.append(f'BSP identity differs from {release} build manifest')
    return dict(ok=not failures, root=str(root), checkedFiles=checked,
                components=[c['id'] for c in manifest['components']], failures=failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--tracked', action='store_true', help='Also require every declared input to be tracked in Git')
    args = parser.parse_args()
    result = verify(args.root, check_tracked=args.tracked)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
