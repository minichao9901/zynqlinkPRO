"""Build the maintained MSC-derived XUsbPs CDC project in firmware/xusbps_cdc."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tx', type=int, default=512)
    ap.add_argument('--depth', type=int, default=16)
    ap.add_argument('--rx-depth', type=int, default=16)
    ap.add_argument('--rx-bytes', type=int, default=512)
    ap.add_argument('--itc', type=int, choices=[0, 1, 2, 4, 8], default=1)
    ap.add_argument('--opt', choices=['0', '3'], default='3')
    ap.add_argument('--sequence', action='store_true')
    args = ap.parse_args()
    if not (32 <= args.tx <= 16384 and args.tx % 32 == 0 and 512 <= args.rx_bytes <= 16384 and args.rx_bytes % 32 == 0 and 1 <= args.depth <= 64 and 1 <= args.rx_depth <= 64):
        ap.error('Invalid size/depth')
    src = ROOT / 'firmware/xusbps_cdc'
    bsp = ROOT / 'reference/legacy_zynq/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0'
    tag = f'tx{args.tx}_d{args.depth}_rx{args.rx_bytes}x{args.rx_depth}_itc{args.itc}_O{args.opt}' + ('_seq' if args.sequence else '')
    out = ROOT / 'build/xusbps_cdc' / tag
    out.mkdir(parents=True, exist_ok=True)
    gcc = Path(r'E:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-none-eabi\bin\arm-none-eabi-gcc.exe')
    flags = ['-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard']
    defines = [f'-DCDC_TX_BYTES={args.tx}', f'-DCDC_TX_DEPTH={args.depth}', f'-DCDC_RX_DEPTH={args.rx_depth}', f'-DCDC_RX_BYTES={args.rx_bytes}', f'-DCDC_ITC={args.itc}', f'-DCDC_FRAME_TEST={int(args.sequence)}']
    objects, logs = [], []
    def run(cmd):
        proc = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, errors='replace')
        logs.append(subprocess.list2cmdline([str(x) for x in cmd]) + '\n' + proc.stdout + proc.stderr)
        (out / 'build.log').write_text('\n'.join(logs), encoding='utf-8')
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
    for p in sorted(src.glob('*.c')):
        obj = out / (p.stem + '.o')
        run([gcc, *flags, '-O' + args.opt, '-g3', '-Wall', '-Wextra', '-I' + str(bsp / 'include'), '-I' + str(src), *defines, '-c', p, '-o', obj])
        objects.append(obj)
    elf = out / 'xusbps_cdc.elf'
    run([gcc, *flags, '-specs=' + str(src / 'Xilinx.spec'), '-Wl,-build-id=none', '-Wl,-T,' + str(src / 'lscript.ld'), '-Wl,-Map,' + str(out / 'xusbps_cdc.map'), '-L' + str(bsp / 'lib'), '-o', elf, *objects, '-Wl,--start-group', '-lxil', '-lgcc', '-lc', '-Wl,--end-group'])
    manifest = {'options': vars(args), 'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir() if p.is_file()}, 'bsp_sha256': hashlib.sha256((bsp / 'lib/libxil.a').read_bytes()).hexdigest(), 'elf_sha256': hashlib.sha256(elf.read_bytes()).hexdigest()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(elf)


if __name__ == '__main__':
    main()
