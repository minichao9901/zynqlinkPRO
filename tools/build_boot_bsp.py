"""Generate/build the dedicated QSPI boot BSP from the versioned boot HDF."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
try:
    from .sdk_runtime import prepare
except ImportError:
    from sdk_runtime import prepare

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True,help='new output directory')
    parser.add_argument('--sdk',type=Path,default=Path('E:/Xilinx/SDK/2018.3'))
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    exe,env=prepare(args.sdk,'hsi')
    # HSI writes ps7_init side products next to the opened HDF. Keep them out
    # of the versioned hardware inputs by opening a byte-identical local copy.
    hardware=out/'hardware';hardware.mkdir()
    for name in ['system.hdf','generate_bsp.tcl']:
        shutil.copyfile(ROOT/'firmware/boot/hardware'/name,hardware/name)
    script=out/'generate.tcl'
    script.write_text('set argv [list {'+(out/'bsp').as_posix()+'}]\nsource {'+
        (hardware/'generate_bsp.tcl').as_posix()+'}\n',encoding='utf8')
    proc=subprocess.run([str(exe),'-mode','batch','-source',str(script)],cwd=out,env=env,capture_output=True,text=True)
    (out/'generate.log').write_text(proc.stdout+proc.stderr,encoding='utf8')
    bsp=out/'bsp'
    if proc.returncode or not (bsp/'Makefile').is_file():
        raise RuntimeError('HSI failed to generate QSPI BSP; see '+str(out/'generate.log'))
    sdk=args.sdk.resolve()
    env['PATH']=str(sdk/'gnu/aarch32/nt/gcc-arm-none-eabi/bin')+';'+str(sdk/'gnuwin/bin')+';'+env['PATH']
    proc=subprocess.run([str(sdk/'gnuwin/bin/make.exe'),'-C',str(bsp),'-j1'],env=env,capture_output=True,text=True)
    (out/'build.log').write_text(proc.stdout+proc.stderr,encoding='utf8')
    library=bsp/'ps7_cortexa9_0/lib/libxil.a'
    if proc.returncode or not library.is_file() or not (bsp/'ps7_cortexa9_0/include/xqspips.h').is_file():
        raise RuntimeError('BSP build failed; see '+str(out/'build.log'))
    report={'bsp':str(bsp),'sdk':str(sdk),'librarySHA256':hashlib.sha256(library.read_bytes()).hexdigest(),
        'hdfSHA256':hashlib.sha256((ROOT/'firmware/boot/hardware/system.hdf').read_bytes()).hexdigest()}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
