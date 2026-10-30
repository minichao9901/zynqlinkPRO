"""Build source-pinned F103ZE acceptance targets at the rated 72 MHz clock."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('kind',choices=('rtt','scope'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--gcc',type=Path,default=Path('E:/Share/env-windows/tools/gnu_gcc/arm_gcc/mingw/bin/arm-none-eabi-gcc.exe'))
    a=p.parse_args()
    source=ROOT/'firmware/target'/('stm32f103_rtt_seq72' if a.kind=='rtt' else 'stm32f103_scope_rated')
    output=a.out.resolve();output.mkdir(parents=True,exist_ok=False)
    sources=[source/'src/main.c',source/'src/startup.c']
    flags=['-mcpu=cortex-m3','-mthumb','-Os','-g3','-gdwarf-4',
           '-ffunction-sections','-fdata-sections','-fno-common','-Wall','-Wextra',
           '-DCPU_HZ=72000000u','-DTARGET_HCLK_MHZ=72','-I'+str(source/'src'),
           '-T'+str(source/'ld/stm32f103ze.ld'),'-nostartfiles','-specs=nano.specs',
           '-specs=nosys.specs','-Wl,--gc-sections','-Wl,-Map='+str(output/'fw.map')]
    if a.kind=='rtt':
        sources.append(source/'segger_rtt/SEGGER_RTT.c')
        flags+=['-I'+str(source/'segger_rtt'),'-DBUFFER_SIZE_UP=32768']
    elf=output/'fw.elf'
    run=subprocess.run([str(a.gcc),*flags,*map(str,sources),'-o',str(elf)],capture_output=True)
    (output/'build.txt').write_bytes(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError('fixture build failed: '+str(output/'build.txt'))
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    manifest={'kind':a.kind,'chip':'STM32F103ZE','cpuHz':72000000,'hseHz':8000000,
              'compiler':subprocess.check_output([str(a.gcc),'--version'],text=True).splitlines()[0],
              'flags':flags,'sourceSha256':{str(f.relative_to(source)):sha(f) for f in source.rglob('*') if f.is_file()},
              'elfSha256':sha(elf),'status':'fresh build; board acceptance pending'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'elf':str(elf),'sha256':sha(elf),'cpuHz':72000000}))


if __name__=='__main__':main()
