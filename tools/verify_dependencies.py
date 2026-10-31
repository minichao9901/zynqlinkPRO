"""Verify vendored build/simulation inputs without a toolchain, USB or network."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root):
    root = root.resolve()
    manifest = json.loads((root / 'docs/required-dependencies.json').read_text(encoding='utf-8'))
    failures = []
    checked = 0
    for component in manifest['components']:
        for relative, expected in component['files'].items():
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
    args = parser.parse_args()
    result = verify(args.root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
