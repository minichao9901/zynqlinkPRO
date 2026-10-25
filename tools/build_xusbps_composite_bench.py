"""Build the composite DAPLink-descriptor USB CDC/WinUSB throughput bench."""
import argparse, hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--opt', choices=['0','3'], default='3'); args = ap.parse_args()
    src = ROOT / 'firmware/xusbps_composite_bench'
    bsp = ROOT / 'reference/legacy_zynq/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0'
    out = ROOT / 'build/xusbps_composite_bench' / f'O{args.opt}'; out.mkdir(parents=True, exist_ok=True)
    gcc = Path(r'E:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-none-eabi\bin\arm-none-eabi-gcc.exe')
    flags = ['-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard']; inc = [src, bsp/'include']
    files = [src/'main.c', src/'bench_app.c', src/'xusbps_ch9.c', src/'xusbps_ch9_storage.c', src/'xusbps_class_cdc.c', src/'xusbps_bos_desc.c']
    logs=[]; objs=[]
    def run(cmd):
        p=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,errors='replace'); logs.append(subprocess.list2cmdline([str(x) for x in cmd])+'\n'+p.stdout+p.stderr); (out/'build.log').write_text('\n'.join(logs),encoding='utf-8')
        if p.returncode: raise RuntimeError(p.stdout+p.stderr)
    for p in files:
        o=out/p.with_suffix('.o').name; run([gcc,*flags,'-O'+args.opt,'-g3','-Wall','-Wextra',*sum((['-I',str(i)] for i in inc),[]),'-c',p,'-o',o]); objs.append(o)
    elf=out/'xusbps_composite_bench.elf'; run([gcc,*flags,'-specs='+str(src/'Xilinx.spec'),'-Wl,-build-id=none','-Wl,-T,'+str(src/'lscript.ld'),'-Wl,-Map,'+str(out/'xusbps_composite_bench.map'),'-L'+str(bsp/'lib'),'-o',elf,*objs,'-Wl,--start-group','-lxil','-lgcc','-lc','-Wl,--end-group'])
    (out/'manifest.json').write_text(json.dumps({'options':vars(args),'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest()},indent=2),encoding='utf-8'); print(elf)
if __name__=='__main__': main()
