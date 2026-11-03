"""Build only: repository-local HAL dependencies, explicit new output directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=HERE.parent/'stm32f103_cdc_trace'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    gcc=Path(shutil.which('arm-none-eabi-gcc'))
    sdk=BASE/'sdk/Drivers';hal=sdk/'STM32F1xx_HAL_Driver'
    startup=sdk/'CMSIS/Device/ST/STM32F1xx/Source/Templates/gcc/startup_stm32f103xe.s'
    sources=[startup,HERE/'src/main.c',HERE/'src/storage.c',BASE/'src/system_stm32f1xx.c',BASE/'src/syscalls.c',BASE/'segger_rtt/SEGGER_RTT.c',BASE/'segger_rtt/SEGGER_RTT_printf.c']
    sources += [hal/f'Src/stm32f1xx_{name}.c' for name in ['hal','hal_cortex','hal_rcc','hal_rcc_ex','hal_gpio','hal_gpio_ex','hal_dma','hal_flash','hal_flash_ex','hal_pwr']]
    sources += [HERE/'vendor/stm32f1xx_hal_spi.c',HERE/'vendor/stm32f1xx_hal_i2c.c']
    includes=[HERE/'src',BASE/'sdk',hal/'Inc',hal/'Inc/Legacy',sdk/'CMSIS/Include',sdk/'CMSIS/Device/ST/STM32F1xx/Include',BASE/'segger_rtt']
    flags=['-mcpu=cortex-m3','-mthumb','-Og','-g3','-gdwarf-4','-fno-inline','-fno-optimize-sibling-calls','-ffunction-sections','-fdata-sections','-fno-common','-Wall','-Wextra','-Wno-unused-parameter','-DSTM32F103xE','-DUSE_HAL_DRIVER','-DHSE_VALUE=8000000','-DRTT_CB_ATTR=__attribute__((section(".rtt_cb"),aligned(4)))']
    flags += ['-I'+str(v) for v in includes]
    objects=[]
    for index,source in enumerate(sources):
        obj=out/f'{index:02}-{source.stem}.o'
        subprocess.run([str(gcc),*flags,'-c',str(source),'-o',str(obj)],check=True);objects.append(obj)
    elf=out/'fw.elf';linker=BASE/'ld/stm32f103ze.ld'
    subprocess.run([str(gcc),*flags,*map(str,objects),'-T'+str(linker),'-specs=nano.specs','-specs=nosys.specs','-Wl,--gc-sections','-Wl,-Map='+str(out/'fw.map'),'-o',str(elf)],check=True)
    def sibling(name):return str(gcc.with_name(name+gcc.suffix))
    for fmt,extension in [('binary','bin'),('ihex','hex')]:subprocess.run([sibling('arm-none-eabi-objcopy'),'-O',fmt,str(elf),str(out/f'fw.{extension}')],check=True)
    for name,args in [('fw.disasm',['-dS',str(elf)]),('fw.symbols',['-n',str(elf)])]:
        exe=sibling('arm-none-eabi-objdump' if name.endswith('disasm') else 'arm-none-eabi-nm')
        with (out/name).open('w',encoding='utf8') as stream:subprocess.run([exe,*args],stdout=stream,check=True)
    subprocess.run([sibling('arm-none-eabi-size'),str(elf)],check=True)
    tracked=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    files=sources+[linker,HERE/'build.py',HERE/'src/storage.h',HERE/'src/stm32f1xx_hal_conf.h']
    files += list((hal/'Inc').rglob('*.h'))+list((sdk/'CMSIS/Include').glob('*.h'))+list((sdk/'CMSIS/Device/ST/STM32F1xx/Include').glob('*.h'))
    manifest=dict(baseRevision=tracked,sourceDirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),target='STM32F103ZE Elite',clock=dict(hse=8000000,cpu=48000000,pclk1=24000000,traceclk=24000000,spi2=1500000,i2c1=100000),flags=flags,compiler=subprocess.check_output([str(gcc),'--version'],text=True).splitlines()[0],
        sourceInputs={str(v.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(v.read_bytes()).hexdigest() for v in sorted(set(files))},
        files={n:dict(bytes=(out/n).stat().st_size,sha256=hashlib.sha256((out/n).read_bytes()).hexdigest()) for n in ['fw.elf','fw.bin','fw.hex']},hardwareValidation='pending; build success is not board acceptance',targetFlashWrites=False,probeQspiWrites=False)
    (out/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')

if __name__=='__main__':main()
