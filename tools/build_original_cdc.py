"""Build the untouched archived CDC source against the local late BSP."""
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
archive = root / 'reference/legacy_zynq'
app = archive / 'PS_CherryUSB_Minichao/PS_CherryUSB_Minichao.sdk/PS_CherryUSB_CDC_speedtest'
bsp = archive / 'ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0'
out = root / 'build/cdc_original'
out.mkdir(exist_ok=True)
shutil.copytree(app / 'src', out / 'src', dirs_exist_ok=True)
gcc = Path(r'E:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-none-eabi\bin\arm-none-eabi-gcc.exe')
flags = ['-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard']
objects, log = [], []

def run(cmd):
    proc = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, errors='replace')
    log.append(subprocess.list2cmdline([str(x) for x in cmd]) + '\n' + proc.stdout + proc.stderr)
    (out / 'build.log').write_text('\n'.join(log), encoding='utf-8')
    if proc.returncode:
        raise RuntimeError(proc.stdout + proc.stderr)

files = [out / 'src/main.c'] + [out / 'src/CherryUSB' / n for n in ['cdc_acm_template.c', 'usb_dc_chipidea.c', 'usbd_core.c', 'usbd_cdc_acm.c']]
for source in files:
    obj = out / (source.stem + '.o')
    run([gcc, *flags, '-O0', '-g3', '-I' + str(bsp / 'include'), '-c', source, '-o', obj])
    objects.append(obj)
run([gcc, *flags, '-specs=' + str(app / 'Debug/Xilinx.spec'), '-Wl,-build-id=none', '-Wl,-T,' + str(out / 'src/lscript.ld'), '-L' + str(bsp / 'lib'), '-o', out / 'cdc_original.elf', *objects, '-Wl,--start-group', '-lxil', '-lgcc', '-lc', '-Wl,--end-group'])
print(out / 'cdc_original.elf')
