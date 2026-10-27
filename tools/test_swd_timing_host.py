"""Native test of production timing configuration C; no USB or board access."""
from pathlib import Path
import os
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'build/swd_timing_host';out.mkdir(parents=True,exist_ok=True)
(out/'DAP_config.h').write_text('''#include <stdint.h>
#include <stddef.h>
#define SLCR_FPGA0_CLK_CTRL 0xf8000170U
#define IO_PLL_HZ 1800000000U
uint32_t Xil_In32(uintptr_t);
void Xil_Out32(uintptr_t,uint32_t);
int ps_set_fclk0_hz(uint32_t);
static inline uint32_t swd_read32(uintptr_t a){return Xil_In32(a);}
static inline void swd_write32(uintptr_t a,uint32_t v){Xil_Out32(a,v);}
''')
cc=['gcc']
if os.name=='nt' and shutil.which('clang'):
    mingw=Path(shutil.which('gcc')).parent.parent
    versions=sorted((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
    cc=['clang','--target=x86_64-w64-windows-gnu','--sysroot='+str(mingw),
        '-B',str(mingw/'bin'),'-L',str(versions[-1])]
exe=out/'timing.exe'
subprocess.run([*cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(out),
    '-I'+str(ROOT/'firmware/xusbps_daplink_dma/DAP/Include'),
    str(ROOT/'tools/tests/swd_timing_test.c'),
    str(ROOT/'firmware/xusbps_daplink_dma/DAP/Source/swd_timing.c'),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True)

# Exercise the actual CLI codec without opening a USB device.
import struct
import swd_timing as cli
reply=bytes([0x90,0,1,0])+struct.pack('<10I',120000000,65536,
    1,78644,393216,196608,327680,0,0,0x20a11)
decoded=cli.decode(reply)
assert decoded['version']==1 and decoded['half_q']==78644 and decoded['epoch']==1
assert cli.sample_word('end',None,131072)==196608
assert cli.sample_word('0','q2',196608)==262144
try:
    cli.sample_word('65536',None,0)
    raise AssertionError('numeric offset overflow accepted')
except ValueError:
    pass
print('PASS timing CLI codec: response layout, independent phase/offset, bounds; no USB access')
