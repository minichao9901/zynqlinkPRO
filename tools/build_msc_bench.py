"""Build the copied Xilinx MSC example with measured cache/sector options."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dcache', choices=['on', 'off'], default='on')
    ap.add_argument('--sector', type=int, choices=[512, 4096], default=4096)
    ap.add_argument('--opt', choices=['0', '3'], default='0')
    ap.add_argument('--itc', choices=['keep', '0', '1', '8'], default='keep')
    args = ap.parse_args()
    original = ROOT / 'reference/xilinx_msc'
    bsp = ROOT / 'reference/legacy_zynq/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0'
    tag = f'sector{args.sector}_dcache{args.dcache}_O{args.opt}_itc{args.itc}'
    out = ROOT / 'build/msc_bench' / tag
    src = out / 'src'
    src.mkdir(parents=True, exist_ok=True)
    manifest = {'options': vars(args), 'original_sha256': {}}
    for p in original.iterdir():
        if p.suffix in ['.c', '.h', '.ld', '.spec']:
            data = p.read_bytes()
            manifest['original_sha256'][p.name] = hashlib.sha256(data).hexdigest()
            (src / p.name).write_bytes(data)
    header = src / 'xusbps_class_storage.h'
    text = header.read_text(encoding='utf-8').replace('#define VFLASH_BLOCK_SIZE\t0x1000', f'#define VFLASH_BLOCK_SIZE\t{args.sector}')
    header.write_text(text, encoding='utf-8')
    # One cache line, published once per SCSI command, not once per 512-byte RX.
    (src / 'msc_stats.h').write_text('''#include "xil_cache.h"
typedef struct { volatile unsigned read_commands, write_commands, read_bytes,
write_bytes, max_read_length, max_write_length, sctlr, reserved; } msc_stats_t;
extern msc_stats_t msc_stats;
''', encoding='utf-8')
    main_c = src / 'xusbps_intr_example.c'
    text = main_c.read_text(encoding='utf-8')
    text = '#include "msc_stats.h"\nmsc_stats_t msc_stats __attribute__((aligned(32)));\n' + text
    startup = '\n'
    if args.dcache == 'off':
        startup += '\tXil_DCacheDisable();\n'
    startup += '\t__asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(msc_stats.sctlr));\n\tXil_DCacheFlushRange((UINTPTR)&msc_stats, sizeof(msc_stats));\n'
    text = text.replace('int main(void)\n{', 'int main(void)\n{' + startup)
    if args.itc != 'keep':
        text = text.replace('\tXUsbPs_Start(UsbInstancePtr);', f'\tXUsbPs_WriteReg(UsbInstancePtr->Config.BaseAddress, XUSBPS_CMD_OFFSET, (XUsbPs_ReadReg(UsbInstancePtr->Config.BaseAddress, XUSBPS_CMD_OFFSET) & ~XUSBPS_CMD_ITC_MASK) | ({int(args.itc)}U << 16));\n\tXUsbPs_Start(UsbInstancePtr);')
    main_c.write_text(text, encoding='utf-8')
    storage = src / 'xusbps_class_storage.c'
    text = '#include "msc_stats.h"\n' + storage.read_text(encoding='utf-8')
    for kind in ['READ', 'WRITE']:
        field = kind.lower()
        needle = '\t\tcase USB_RBC_' + kind + ':\n'
        addition = f'''            {{
                unsigned len = htons(((SCSI_READ_WRITE *)CBW->CBWCB)->length) * VFLASH_BLOCK_SIZE;
                msc_stats.{field}_commands++;
                msc_stats.{field}_bytes += len;
                if (len > msc_stats.max_{field}_length) msc_stats.max_{field}_length = len;
                Xil_DCacheFlushRange((UINTPTR)&msc_stats, sizeof(msc_stats));
            }}
'''
        # The second WRITE case is the DATA phase; instrument only the CBW.
        text = text.replace(needle, needle + addition, 1)
    storage.write_text(text, encoding='utf-8')
    gcc = Path(r'E:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-none-eabi\bin\arm-none-eabi-gcc.exe')
    flags = ['-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard']
    logs, objects = [], []
    def run(cmd):
        proc = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, errors='replace')
        logs.append(subprocess.list2cmdline([str(x) for x in cmd]) + '\n' + proc.stdout + proc.stderr)
        (out / 'build.log').write_text('\n'.join(logs), encoding='utf-8')
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
    for p in sorted(src.glob('*.c')):
        obj = out / (p.stem + '.o')
        run([gcc, *flags, '-O' + args.opt, '-g3', '-Wall', '-I' + str(bsp / 'include'), '-c', p, '-o', obj])
        objects.append(obj)
    elf = out / 'msc_bench.elf'
    run([gcc, *flags, '-specs=' + str(src / 'Xilinx.spec'), '-Wl,-build-id=none', '-Wl,-T,' + str(src / 'lscript.ld'), '-Wl,-Map,' + str(out / 'msc_bench.map'), '-L' + str(bsp / 'lib'), '-o', elf, *objects, '-Wl,--start-group', '-lxil', '-lgcc', '-lc', '-Wl,--end-group'])
    manifest['elf_sha256'] = hashlib.sha256(elf.read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(elf)


if __name__ == '__main__':
    main()
