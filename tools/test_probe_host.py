"""Compile and run production probe services with mocked USB and target RAM."""
from pathlib import Path
import subprocess
import os
import shutil

root = Path(__file__).resolve().parents[1]
out = root/'build/probe_host'
out.mkdir(parents=True, exist_ok=True)
for name in ['xusbps', 'xusbps_hw', 'xusbps_endpoint', 'xil_types', 'xstatus',
             'xparameters', 'xil_cache', 'xil_exception', 'xil_io', 'xtime_l']:
    (out/f'{name}.h').write_text('#include "probe_host_platform.h"\n')
for name in ['DAP','DAP_config']:
    (out/f'{name}.h').write_text('#include "probe_target_platform.h"\n')
exe = out/'probe_host.exe'
compiler=['gcc']
if os.name=='nt' and shutil.which('clang') and shutil.which('gcc'):
    mingw=Path(shutil.which('gcc')).parent.parent
    libs=list((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
    compiler=['clang','--target=x86_64-w64-windows-gnu','-isystem',str(mingw/'include'),
              '-L'+str(mingw/'lib'),'-L'+str(libs[-1])]
descriptor_source=(root/'firmware/xusbps_daplink_dma/xusbps_ch9_storage.c').read_text(encoding='utf-8')
(out/'descriptor_under_test.c').write_text(descriptor_source.split('int XUsbPs_DapResetEndpoints(')[0],encoding='utf-8')
for name in ['probe_host', 'probe_target', 'probe_descriptor', 'probe_jtag']:
    exe=out/(name+'.exe')
    subprocess.run([*compiler, '-std=c11', '-O2', '-Wall', '-Wextra',
                    '-I'+str(out), '-I'+str(root/'tools/tests'), '-I'+str(root/'firmware/xusbps_daplink_dma'),
                    '-I'+str(root/'firmware/xusbps_daplink_dma/DAP/Include'),
                    str(root/'tools/tests'/(name+'_test.c')), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=30)
