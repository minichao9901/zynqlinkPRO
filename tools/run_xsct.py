"""Run the archived XSCT with its DLLs local to this workspace.

Windows loader failed with 0xc0000135 on the original installation. Copy only
SDK-supplied import dependencies next to a local launcher; no system DLL changes.
"""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import pefile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('script', type=Path)
    ap.add_argument('script_args', nargs='*')
    ap.add_argument('--sdk', type=Path, default=Path(r'E:\Xilinx\SDK\2018.3'))
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / 'build/xilinx_runtime'
    out.mkdir(parents=True, exist_ok=True)
    sdk = args.sdk
    search = [sdk / p for p in ['lib/win64.o', 'bin/unwrapped/win64.o', 'tps/win64']]
    seen = set()

    def copydeps(p):
        if p.name.lower() in seen:
            return
        seen.add(p.name.lower())
        destination = out / p.name
        if not destination.exists() or destination.stat().st_size != p.stat().st_size:
            shutil.copy2(p, destination)
        pe = pefile.PE(str(p), fast_load=True)
        pe.parse_data_directories(directories=[1])
        for imp in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
            name = imp.dll.decode()
            if name.lower().startswith(('api-', 'ext-')):
                continue
            match = next((d / name for d in search if (d / name).is_file()), None)
            if match:
                copydeps(match)
        pe.close()

    copydeps(sdk / 'bin/unwrapped/win64.o/tclsh85t.exe')
    copydeps(sdk / 'lib/win64.o/libtcltcf.dll')
    copydeps(sdk / 'bin/unwrapped/win64.o/hw_server.exe')
    for name in ['ftd2xx.dll', 'djtg.dll', 'dmgr.dll', 'dpcomm.dll']:
        match = next((d / name for d in search if (d / name).is_file()), None)
        if match:
            copydeps(match)
    env = os.environ.copy()
    env.update({
        'RDI_APPROOT': str(sdk), 'RDI_DATADIR': str(sdk / 'data'),
        'RDI_BINDIR': str(sdk / 'bin/unwrapped/win64.o'),
        'RDI_LIBDIR': str(sdk / 'lib/win64.o'),
        'TCL_LIBRARY': str(sdk / 'tps/tcl/tcl8.5'),
        'TCLLIBPATH': ' '.join('{' + str(p).replace('\\', '/') + '}' for p in [out, *[sdk / x for x in ['scripts/xsct', 'scripts/xsct/xsdb', 'scripts/xsct/tcf', 'tps/tcl/tcl8.5', 'tps/tcl/tcllib1.11.1']]]),
    })
    bootstrap = out / 'bootstrap.tcl'
    bootstrap.write_text('package require xsdb\nnamespace import xsdb::*\nset script [lindex $argv 0]\nset argv [lrange $argv 1 end]\nsource $script\n', encoding='utf-8')
    def server_ready():
        try:
            with socket.create_connection(('127.0.0.1', 3121), timeout=0.2):
                return True
        except OSError:
            return False
    if not server_ready():
        with (out / 'hw_server.log').open('w') as log:
            process = subprocess.Popen([str(out / 'hw_server.exe'), '-s', 'tcp:127.0.0.1:3121'], env=env,
                                       stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        (out / 'hw_server.pid').write_text(str(process.pid))
        for _ in range(30):
            if server_ready():
                break
            if process.poll() is not None:
                raise RuntimeError((out / 'hw_server.log').read_text(errors='replace'))
            time.sleep(0.1)
    proc = subprocess.run([str(out / 'tclsh85t.exe'), str(bootstrap), str(args.script.resolve()), *args.script_args], env=env)
    raise SystemExit(proc.returncode)


if __name__ == '__main__':
    main()
