"""Repair missing app-local DLLs from Vivado's own files, then use its launcher.

Existing installation files are never overwritten. Added DLL paths are recorded
in build/vivado_runtime/installation_added_files.json for reversible cleanup.
"""
import os
from pathlib import Path
import subprocess
import sys
import shutil
import pefile
import json

v = Path(r'E:\Xilinx\Vivado\2018.3')
env = os.environ.copy()
paths = [v/'bin/unwrapped/win64.o', v/'lib/win64.o', v/'tps/win64',
         v/'bin/unwrapped/win64.o/Microsoft.VC140.CRT', v/'tps/win64/jre9.0.4/bin/server', v/'tps/win64/jre9.0.4/bin']
env['PATH'] = os.pathsep.join(str(p) for p in paths) + os.pathsep + env['PATH']
work_root = Path(os.environ.get('ZYNQLINK_WORK_DIR', str(Path(__file__).resolve().parents[2]/'zynqlinkPRO-work')))
runtime = work_root/'runtime/vivado'
runtime.mkdir(parents=True, exist_ok=True)
tmp = work_root/'tmp/vivado'
tmp.mkdir(exist_ok=True)
env['TEMP'] = env['TMP'] = str(tmp)
seen = set()
def copydeps(p):
    if p.name.lower() in seen: return
    seen.add(p.name.lower())
    dest = runtime/p.name
    if not dest.exists(): shutil.copy2(p, dest)
    pe = pefile.PE(str(p), fast_load=True)
    pe.parse_data_directories(directories=[1])
    for i in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        q = next((d/i.dll.decode() for d in paths if (d/i.dll.decode()).is_file()), None)
        if q: copydeps(q)
    pe.close()
copydeps(v/'bin/unwrapped/win64.o/vivado.exe')
copydeps(v/'bin/unwrapped/win64.o/srcscanner.exe')
for dll in (v/'lib/win64.o').glob('*.dll'):
    copydeps(dll)
record = runtime/'installation_added_files.json'
added = json.loads(record.read_text()) if record.exists() else []
for dll in runtime.glob('*.dll'):
    dest = v/'bin/unwrapped/win64.o'/dll.name
    if not dest.exists():
        shutil.copy2(dll, dest)
        added.append(str(dest))
record.write_text(json.dumps(added, indent=2))
env['PATH'] = str(runtime) + os.pathsep + env['PATH']
env.update(RDI_APPROOT=str(v), XILINX_VIVADO=str(v), RDI_DATADIR=str(v/'data'),
           HDI_APPROOT=str(v), RDI_PLATFORM='win64', RDI_OPT_EXT='.o', RDI_BINROOT=str(v/'bin'),
           RDI_BINDIR=str(v/'bin'), RDI_LIBDIR=str(v/'lib/win64.o'),
           RDI_JAVAROOT=str(v/'tps/win64/jre9.0.4'), TCL_LIBRARY=str(v/'tps/tcl/tcl8.5'))
for key in ('RDI_APPROOT','XILINX_VIVADO','RDI_DATADIR','HDI_APPROOT','RDI_BINROOT','RDI_BINDIR','RDI_LIBDIR','RDI_JAVAROOT','TCL_LIBRARY'):
    env[key] = env[key].replace('\\','/')
overlay = runtime.parent/'vivado_overlay'
env['RDI_LIBDIR'] = (v/'lib/win64.o').as_posix()
p = subprocess.run([str(v/'bin/vivado.bat'), *sys.argv[1:]], env=env)
print('Vivado exit:', p.returncode)
raise SystemExit(p.returncode)
