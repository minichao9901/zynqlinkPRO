"""Copy a patched OpenOCD plus matching DLLs into a workspace-local runtime.

No global PATH, system DLL, or reference OpenOCD installation is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pefile

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--exe', type=Path, required=True)
ap.add_argument('--dll-dir', type=Path, default=Path('C:/msys64/mingw64/bin'))
ap.add_argument('--output', type=Path, default=Path('build/openocd_runtime'))
a = ap.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
machine = pefile.PE(str(a.exe), fast_load=True).FILE_HEADER.Machine
copied = {}
system_dir = Path('C:/Windows/System32')

def copy_dependencies(source):
    key = source.name.lower()
    if key in copied:
        return
    pe = pefile.PE(str(source))
    if pe.FILE_HEADER.Machine != machine:
        raise RuntimeError(f'Architecture mismatch: {source}')
    target = a.output/source.name
    shutil.copy2(source, target)
    copied[key] = hashlib.sha256(target.read_bytes()).hexdigest()
    for imp in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        name = imp.dll.decode()
        dependency = a.dll_dir/name
        if dependency.exists():
            copy_dependencies(dependency)
        elif not (system_dir/name).exists() and not name.lower().startswith(('api-', 'ext-')):
            raise RuntimeError(f'Missing dependency: {name}')
    pe.close()

copy_dependencies(a.exe.resolve())
exe = (a.output/a.exe.name).resolve()
p = subprocess.run([str(exe), '--version'], capture_output=True, text=True, timeout=15)
if p.returncode:
    raise RuntimeError(f'OpenOCD failed: 0x{p.returncode & 0xffffffff:08x}\n{p.stdout}{p.stderr}')
(a.output/'runtime.json').write_text(json.dumps(copied, indent=2))
print(str(exe))
print(p.stderr.strip())
