"""Build the isolated XUsbPs CMSIS-DAP/CDC application."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--opt', choices=['0', '3'], default='3')
    ap.add_argument('--project', choices=['xusbps_daplink', 'xusbps_daplink_dma'], default='xusbps_daplink')
    ap.add_argument('--trace', action='store_true', help='Enable DMA firmware timing trace and MMIO diagnostics')
    ap.add_argument('--usb-trace', action='store_true', help='Trace USB events without per-MMIO diagnostics')
    ap.add_argument('--experimental-zero-idle',action='store_true',
                    help='DMA firmware only: allow unproven zero-idle timing; default clamps to one')
    ap.add_argument('--max-swclk-hz', type=int,
                    help='Conservative firmware limit; cannot exceed the verified timing limit')
    ap.add_argument('--bsp', default=None,
                    help='BSP directory (default: reference/legacy_zynq/.../usb_bsp/ps7_cortexa9_0); '
                         'a BSP root containing ps7_cortexa9_0 is also accepted')
    ap.add_argument('--gcc', default=r'E:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-none-eabi\bin\arm-none-eabi-gcc.exe')
    args = ap.parse_args()
    src = ROOT / 'firmware' / args.project
    if args.bsp:
        bsp = Path(args.bsp)
        if (bsp / 'ps7_cortexa9_0').is_dir():
            bsp = bsp / 'ps7_cortexa9_0'
    else:
        bsp = ROOT / 'reference/legacy_zynq/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0'
    out = ROOT / 'build' / args.project / f'O{args.opt}'
    out.mkdir(parents=True, exist_ok=True)
    gcc = Path(args.gcc)
    flags = ['-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard']
    verified_clock = None
    if args.project == 'xusbps_daplink_dma':
        flags += ['-DDAP_ALLOW_ZERO_IDLE='+str(int(args.experimental_zero_idle))]
        flags += ['-DDAP_ENABLE_TRACE=' + str(int(args.trace or args.usb_trace)), '-DDAP_MMIO_DIAGNOSTICS=' + str(int(args.trace))]
        timing_path = ROOT / 'build/fpga_dma_global/verified_clock.json'
        max_swclk = 60000000
        if timing_path.exists():
            verified_clock = json.loads(timing_path.read_text())
            max_swclk = min(90000000, int(verified_clock['FCLK_max_Hz']) // 2)
        if args.max_swclk_hz is not None:
            if args.max_swclk_hz <= 0 or args.max_swclk_hz > max_swclk:
                ap.error(f'--max-swclk-hz must be between 1 and {max_swclk}')
            max_swclk = args.max_swclk_hz
        flags += ['-DDAP_MAX_SWCLK_HZ=' + str(max_swclk)]
    includes = [src, src / 'DAP/Include', src / 'DAP/Source', bsp / 'include']
    cfiles = sorted(src.rglob('*.c'))
    objects = []
    logs = []

    def run(cmd):
        p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, errors='replace')
        logs.append(subprocess.list2cmdline([str(x) for x in cmd]) + '\n' + p.stdout + p.stderr)
        (out / 'build.log').write_text('\n'.join(logs), encoding='utf-8')
        if p.returncode:
            raise RuntimeError(p.stdout + p.stderr)

    for p in cfiles:
        obj = out / (p.relative_to(src).with_suffix('.o'))
        obj.parent.mkdir(parents=True, exist_ok=True)
        run([gcc, *flags, '-O' + args.opt, '-g3', '-Wall', '-Wextra', *sum((['-I', str(x)] for x in includes), []), '-c', p, '-o', obj])
        objects.append(obj)

    elf = out / (args.project + '.elf')
    run([gcc, *flags, '-specs=' + str(src / 'Xilinx.spec'), '-Wl,-build-id=none', '-Wl,-T,' + str(src / 'lscript.ld'), '-Wl,-Map,' + str(out / 'xusbps_daplink.map'), '-L' + str(bsp / 'lib'), '-o', elf, *objects, '-Wl,--start-group', '-lxil', '-lgcc', '-lc', '-Wl,--end-group'])
    manifest = {
        'options': vars(args),
        'verified_fpga_clock': verified_clock,
        'source_sha256': {str(p.relative_to(src)): hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*') if p.is_file()},
        'bsp_sha256': hashlib.sha256((bsp / 'lib/libxil.a').read_bytes()).hexdigest(),
        'elf_sha256': hashlib.sha256(elf.read_bytes()).hexdigest(),
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(elf)


if __name__ == '__main__':
    main()
