"""Build an isolated CDC experiment with the archived SDK 2018.3 BSP.

Never writes to the archive. Generated source, provenance and ELF stay in build/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Archive source differs from expected: {old[:90]!r}")
    return text.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, default=ROOT / 'reference/legacy_zynq')
    ap.add_argument('--sdk', type=Path, default=Path(r'E:\Xilinx\SDK\2018.3'))
    ap.add_argument('--tx', type=int, default=512)
    ap.add_argument('--rx', type=int, default=512)
    ap.add_argument('--itc', type=int, choices=[0, 1, 2, 4, 8, 16, 32, 64], default=0)
    ap.add_argument('--zlp', type=int, choices=[0, 1], default=0)
    ap.add_argument('--callback-tx', type=int, choices=[0, 1], default=1)
    ap.add_argument('--opt', choices=['0', '1', '2', '3'], default='0')
    ap.add_argument('--memory-mode', choices=['legacy', 'isolated', 'cached', 'hybrid'], default='legacy')
    ap.add_argument('--pattern', choices=['ramp', 'sequence'], default='ramp')
    args = ap.parse_args()
    if not (1 <= args.tx <= 131072 and 512 <= args.rx <= 131072 and args.rx % 512 == 0):
        ap.error('tx must be 1..131072; rx must be 512..131072 and a multiple of 512')
    if args.pattern == 'sequence' and (args.tx != 512 or args.rx != 512 or args.zlp):
        ap.error('sequence mode requires tx=rx=512 and zlp=0')
    sdk_workspace = args.archive / 'PS_CherryUSB_Minichao/PS_CherryUSB_Minichao.sdk'
    original = sdk_workspace / 'PS_CherryUSB_CDC_speedtest/src'
    # The early cherryusb_bsp archive has tracing calls inside cache routines.
    # Use the later board BSP whose cache implementation has no tracing hooks.
    bsp = args.archive / 'ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0'
    tag = f'tx{args.tx}_rx{args.rx}_itc{args.itc}_zlp{args.zlp}_cb{args.callback_tx}_O{args.opt}_mem{args.memory_mode}'
    if args.pattern == 'sequence':
        tag += '_seq'
    out = ROOT / 'build' / 'cdc_bench' / tag
    src = out / 'src'
    src.mkdir(parents=True, exist_ok=True)
    manifest = {'archive': str(original), 'bsp': str(bsp), 'options': vars(args).copy(), 'original_sha256': {}}
    manifest['bsp_libxil_sha256'] = hashlib.sha256((bsp / 'lib/libxil.a').read_bytes()).hexdigest()
    manifest['options'] = {k: str(v) if isinstance(v, Path) else v for k, v in manifest['options'].items()}

    def read(relative):
        p = original / relative
        data = p.read_bytes()
        manifest['original_sha256'][relative] = hashlib.sha256(data).hexdigest()
        return data.decode('utf-8').replace('\r\n', '\n')

    # Include only the CDC stack. Preserve upstream licenses in the copied files.
    for p in (original / 'CherryUSB').iterdir():
        if p.suffix == '.h' or p.name in ('usbd_core.c', 'usbd_cdc_acm.c', 'usb_dc_chipidea.c', 'cdc_acm_template.c'):
            (src / p.name).write_text(read('CherryUSB/' + p.name), encoding='utf-8')
    (src / 'bench_config.h').write_bytes((ROOT / 'firmware/cdc_bench/bench_config.h').read_bytes())
    config = (src / 'usb_config.h').read_text(encoding='utf-8')
    config = config.replace('#define CONFIG_USB_ALIGN_SIZE 4', '#define CONFIG_USB_ALIGN_SIZE 32')
    (src / 'usb_config.h').write_text(config, encoding='utf-8')
    driver = (src / 'usb_dc_chipidea.c').read_text(encoding='utf-8')
    driver = '#include "bench_config.h"\n' + driver
    driver = replace_once(driver, '//    ptr->USBCMD &= ~USB_USBCMD_ITC_MASK;',
                          'ptr->USBCMD = (ptr->USBCMD & ~USB_USBCMD_ITC_MASK) | ((uint32_t)BENCH_ITC << 16);')
    # Publish completed descriptors before handing them to the DMA engine.
    driver = replace_once(driver, '    chipidea_edpt_xfer(USB_OTG_DEV, ep_idx);',
                          '    __asm__ volatile("dsb sy" ::: "memory");\n    chipidea_edpt_xfer(USB_OTG_DEV, ep_idx);')
    if args.memory_mode in ('cached', 'hybrid'):
        # Keep code, normal data, USB payloads and descriptors cacheable. Explicit
        # ownership transitions mirror XUsbPs: clean before DMA, invalidate on
        # completed DMA, and do not modify an active descriptor.
        driver = replace_once(driver, '    Xil_MemMap((uint32_t)&g_chipidea_udc[0], sizeof(struct chipidea_udc), NORM_NONCACHE);', '')
        driver = replace_once(driver, '    Xil_MemMap((uint32_t)&_dcd_data0, sizeof(dcd_data_t), NORM_NONCACHE);', '')
        driver = replace_once(driver, '    memset(g_chipidea_udc[busid].dcd_data, 0, sizeof(dcd_data_t));',
                              '    memset(g_chipidea_udc[busid].dcd_data, 0, sizeof(dcd_data_t));\n    Xil_DCacheFlushRange((UINTPTR)g_chipidea_udc[busid].dcd_data, sizeof(dcd_data_t));')
        driver = replace_once(driver, '    dcd_data->qtd[0].int_on_complete =1;',
                              '    dcd_data->qtd[0].int_on_complete =1;\n    Xil_DCacheFlushRange((UINTPTR)dcd_data, sizeof(dcd_data_t));')
        driver = replace_once(driver, '    __chipidea_edpt_open(USB_OTG_DEV, ep_addr, ep_type);',
                              '    Xil_DCacheFlushRange((UINTPTR)p_qhd, sizeof(dcd_qhd_t));\n    __chipidea_edpt_open(USB_OTG_DEV, ep_addr, ep_type);')
        driver = replace_once(driver, '    p_qhd->qtd_overlay.next = (uint32_t)first_p_qtd;',
                              '''    Xil_DCacheFlushRange((UINTPTR)&dcd_data->qtd[ep_idx * QTD_COUNT_EACH_ENDPOINT], i * sizeof(dcd_qtd_t));
    Xil_DCacheInvalidateRange((UINTPTR)p_qhd, sizeof(dcd_qhd_t));
    p_qhd->qtd_overlay.halted = 0;
    p_qhd->qtd_overlay.active = 0;
    p_qhd->qtd_overlay.next = (uint32_t)first_p_qtd;
    Xil_DCacheFlushRange((UINTPTR)p_qhd, sizeof(dcd_qhd_t));''')
        driver = replace_once(driver, '    g_chipidea_udc[busid].in_ep[ep_idx].xfer_buf = (uint8_t *)data;',
                              '    if (data_len) Xil_DCacheFlushRange((UINTPTR)data, data_len);\n    g_chipidea_udc[busid].in_ep[ep_idx].xfer_buf = (uint8_t *)data;')
        driver = replace_once(driver, '    g_chipidea_udc[busid].out_ep[ep_idx].xfer_buf = (uint8_t *)data;',
                              '    if (data_len) Xil_DCacheFlushRange((UINTPTR)data, data_len);\n    g_chipidea_udc[busid].out_ep[ep_idx].xfer_buf = (uint8_t *)data;')
        driver = replace_once(driver, '                    while (1) {',
                              '                    while (1) {\n                        Xil_DCacheInvalidateRange((UINTPTR)p_qtd, sizeof(dcd_qtd_t));')
        driver = replace_once(driver, '                            usbd_event_ep_out_complete_handler(busid, ep_addr, transfer_len);',
                              '                            if (transfer_len) Xil_DCacheInvalidateRange((UINTPTR)g_chipidea_udc[busid].out_ep[ep_idx / 2].xfer_buf, transfer_len);\n                            usbd_event_ep_out_complete_handler(busid, ep_addr, transfer_len);')
        driver = replace_once(driver, '            usbd_event_ep0_setup_complete_handler(busid, (uint8_t *)&qhd0->setup_request);',
                              '            Xil_DCacheInvalidateRange((UINTPTR)qhd0, sizeof(dcd_qhd_t));\n            usbd_event_ep0_setup_complete_handler(busid, (uint8_t *)&qhd0->setup_request);')
        if args.memory_mode == 'hybrid':
            driver = replace_once(driver, 'static USB_NOCACHE_RAM_SECTION __attribute__((aligned(2048))) dcd_data_t _dcd_data0;',
                                  'static __attribute__((section(".usb_descriptors"), aligned(2048))) dcd_data_t _dcd_data0;')
            descriptor_operations = [
                'Xil_DCacheFlushRange((UINTPTR)g_chipidea_udc[busid].dcd_data, sizeof(dcd_data_t));',
                'Xil_DCacheFlushRange((UINTPTR)dcd_data, sizeof(dcd_data_t));',
                'Xil_DCacheFlushRange((UINTPTR)p_qhd, sizeof(dcd_qhd_t));',
                'Xil_DCacheFlushRange((UINTPTR)&dcd_data->qtd[ep_idx * QTD_COUNT_EACH_ENDPOINT], i * sizeof(dcd_qtd_t));',
                'Xil_DCacheInvalidateRange((UINTPTR)p_qhd, sizeof(dcd_qhd_t));',
                'Xil_DCacheInvalidateRange((UINTPTR)p_qtd, sizeof(dcd_qtd_t));',
                'Xil_DCacheInvalidateRange((UINTPTR)qhd0, sizeof(dcd_qhd_t));',
            ]
            for operation in descriptor_operations:
                if operation not in driver:
                    raise ValueError('Missing descriptor maintenance operation ' + operation)
                driver = driver.replace(operation, '__asm__ volatile("dsb sy" ::: "memory");')
    (src / 'usb_dc_chipidea.c').write_text(driver, encoding='utf-8')
    cdc = (src / 'cdc_acm_template.c').read_text(encoding='utf-8')
    cdc = '#include "bench_config.h"\n' + cdc
    cdc = replace_once(cdc, "    memcpy(&write_buffer[0], data, 10);\n    memset(&write_buffer[10], 'a', 128*1024-10);", '')
    cdc = replace_once(cdc, '    const uint8_t data[10] = { 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x30 };', '')
    cdc = cdc.replace('read_buffer[128*1024]', 'read_buffer[BENCH_RX_BYTES]')
    cdc = cdc.replace('write_buffer[128*1024]', 'write_buffer[BENCH_TX_BYTES]')
    cdc = cdc.replace('read_buffer, 128*1024', 'read_buffer, BENCH_RX_BYTES')
    cdc = cdc.replace('write_buffer, 128*1024', 'write_buffer, BENCH_TX_BYTES')
    cdc = cdc.replace('    USB_LOG_RAW("actual out len:%d\\r\\n", (unsigned int)nbytes);',
                      '    bench_rx_bytes += nbytes; bench_rx_completions++;')
    cdc = cdc.replace('    USB_LOG_RAW("actual in len:%d\\r\\n", (unsigned int)nbytes);',
                      '    bench_tx_bytes += nbytes; bench_tx_completions++;')
    cdc = replace_once(cdc, 'volatile bool ep_tx_busy_flag = false;', '''volatile bool ep_tx_busy_flag = false;
USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t bench_rx_bytes;
USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t bench_tx_bytes;
USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t bench_rx_completions;
USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t bench_tx_completions;
USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t bench_submit_errors;
USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t bench_sctlr;
volatile uint8_t dtr_enable = 0;
static void bench_submit(uint8_t busid)
{
    ep_tx_busy_flag = true;
    if (usbd_ep_start_write(busid, CDC_IN_EP, write_buffer, BENCH_TX_BYTES) != 0) {
        bench_submit_errors++;
        ep_tx_busy_flag = false;
    }
}''')
    cdc = replace_once(cdc, 'volatile uint8_t dtr_enable = 0;\n\nvoid usbd_cdc_acm_set_dtr',
                      'void usbd_cdc_acm_set_dtr')
    if args.pattern == 'sequence':
        helpers = '''
USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t bench_rx_verify_errors;
USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t bench_rx_expected_seq;
static uint32_t bench_tx_seq;
static void bench_fill_frame(void)
{
    uint32_t i, seq = bench_tx_seq++;
    uint32_t *header = (uint32_t *)write_buffer;
    header[0] = 0x30434443U; header[1] = seq; header[2] = 512U; header[3] = ~seq;
    for (i = 16U; i < 512U; ++i) write_buffer[i] = (uint8_t)(seq + i * 17U + (i >> 3));
}
static void bench_verify_rx(uint32_t len)
{
    uint32_t i, seq, bad = 0;
    const uint32_t *header = (const uint32_t *)read_buffer;
    if (len != 512U) { bench_rx_verify_errors++; return; }
    seq = header[1];
    if (header[0] != 0x30434443U || header[2] != 512U || header[3] != ~seq || seq != bench_rx_expected_seq) bad = 1;
    for (i = 16U; i < 512U; ++i) {
        if (read_buffer[i] != (uint8_t)(seq + i * 17U + (i >> 3))) bad = 1;
    }
    bench_rx_expected_seq = seq + 1U;
    if (bad) bench_rx_verify_errors++;
}
'''
        cdc = replace_once(cdc, 'static void bench_submit(uint8_t busid)', helpers + '\nstatic void bench_submit(uint8_t busid)')
        cdc = replace_once(cdc, 'static void bench_submit(uint8_t busid)\n{\n    ep_tx_busy_flag = true;', 'static void bench_submit(uint8_t busid)\n{\n    bench_fill_frame();\n    ep_tx_busy_flag = true;')
        cdc = replace_once(cdc, '    bench_rx_bytes += nbytes; bench_rx_completions++;',
                          '    bench_rx_bytes += nbytes; bench_rx_completions++;\n    bench_verify_rx(nbytes);')
    if args.memory_mode in ('cached', 'hybrid'):
        cdc = cdc.replace('USB_NOCACHE_RAM_SECTION USB_MEM_ALIGNX volatile uint32_t', '__attribute__((section(".bench_stats"), aligned(32))) volatile uint32_t')
    cdc = replace_once(cdc, 'if ((nbytes % usbd_get_ep_mps(busid, ep)) == 0 && nbytes)',
                      'if (BENCH_ZLP && (nbytes % usbd_get_ep_mps(busid, ep)) == 0 && nbytes)')
    cdc = replace_once(cdc, '        ep_tx_busy_flag = false;\n    }\n}\n\n/*!< endpoint call back */',
                      '''        ep_tx_busy_flag = false;
        if (BENCH_CALLBACK_TX && dtr_enable) { bench_submit(busid); }
    }
}

/*!< endpoint call back */''')
    # Constant byte ramp: repeats each transfer; binary host validation is optional.
    cdc = replace_once(cdc, 'void cdc_acm_init(uint8_t busid, uintptr_t reg_base)\n{',
                      '''void cdc_acm_init(uint8_t busid, uintptr_t reg_base)
{
    uint32_t i;
    for (i = 0; i < BENCH_TX_BYTES; ++i) { write_buffer[i] = (uint8_t)i; }''')
    start = cdc.index('void cdc_acm_data_send_with_dtr_test(uint8_t busid)')
    cdc = cdc[:start] + '''void cdc_acm_data_send_with_dtr_test(uint8_t busid)
{
    if (dtr_enable && !ep_tx_busy_flag && usb_device_is_configured(busid)) {
        bench_submit(busid);
    }
}
'''
    # IRQ refills only an already-busy stream. Main starts only an idle stream;
    # callback-TX mode publishes idle only after the stream has stopped.
    (src / 'cdc_acm_template.c').write_text(cdc, encoding='utf-8')
    main_c = read('main.c').replace('"CherryUSB/usbd_core.h"', '"usbd_core.h"')
    # Map an entire dedicated 1 MiB region, keeping code and ordinary data cached.
    main_c = main_c.replace('#include "usbd_core.h"', '#include "usbd_core.h"\n#include "xil_mmu.h"\nextern char __noncacheable_start[], __noncacheable_end[];')
    if args.memory_mode in ('cached', 'hybrid'):
        main_c = main_c.replace('extern char __noncacheable_start[], __noncacheable_end[];', 'extern char __bench_stats_start[], __bench_stats_end[];')
        mapping = '\tXil_MemMap((UINTPTR)__bench_stats_start, (size_t)(__bench_stats_end - __bench_stats_start), NORM_NONCACHE);\n'
        if args.memory_mode == 'hybrid':
            main_c = main_c.replace('extern char __bench_stats_start[], __bench_stats_end[];', 'extern char __bench_stats_start[], __bench_stats_end[];\nextern char __usb_descriptors_start[], __usb_descriptors_end[];')
            mapping = '\tXil_MemMap((UINTPTR)__usb_descriptors_start, (size_t)(__usb_descriptors_end - __usb_descriptors_start), NORM_NONCACHE);\n' + mapping
    else:
        mapping = '\tXil_MemMap((UINTPTR)__noncacheable_start, (size_t)(__noncacheable_end - __noncacheable_start), NORM_NONCACHE);\n'
    mapping += '\textern volatile uint32_t bench_sctlr;\n\t__asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(bench_sctlr));\n'
    main_c = replace_once(main_c, '\tcdc_acm_init(0x00,0xE0002000UL);', mapping + '\tcdc_acm_init(0x00,0xE0002000UL);')
    (src / 'main.c').write_text(main_c, encoding='utf-8')
    ld = read('lscript.ld')
    if args.memory_mode == 'isolated':
        ld = replace_once(ld, '.noncacheable : {', '.noncacheable ALIGN(0x100000) : {')
        ld = replace_once(ld, '    __noncacheable_end = .;', '    . = ALIGN(0x100000);\n    __noncacheable_end = .;')
    if args.memory_mode in ('cached', 'hybrid'):
        ld = replace_once(ld, '.bss (NOLOAD) : {', '''.bench_stats ALIGN(0x100000) : {
    __bench_stats_start = .;
    KEEP(*(.bench_stats))
    . = ALIGN(0x100000);
    __bench_stats_end = .;
} > ps7_ddr_0

.bss (NOLOAD) : {''')
        if args.memory_mode == 'hybrid':
            ld = replace_once(ld, '.bench_stats ALIGN(0x100000) : {', '''.usb_descriptors ALIGN(0x100000) : {
    __usb_descriptors_start = .;
    KEEP(*(.usb_descriptors))
    . = ALIGN(0x100000);
    __usb_descriptors_end = .;
} > ps7_ddr_0

.bench_stats ALIGN(0x100000) : {''')
    (src / 'lscript.ld').write_text(ld, encoding='utf-8')
    gcc = args.sdk / 'gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
    flags = ['-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard']
    defines = [f'-DBENCH_TX_BYTES={args.tx}', f'-DBENCH_RX_BYTES={args.rx}',
               f'-DBENCH_ITC={args.itc}', f'-DBENCH_ZLP={args.zlp}', f'-DBENCH_CALLBACK_TX={args.callback_tx}']
    log = []
    def run(argv):
        proc = subprocess.run([str(x) for x in argv], capture_output=True, text=True, errors='replace')
        log.append(subprocess.list2cmdline([str(x) for x in argv]) + '\n' + proc.stdout + proc.stderr)
        (out / 'build.log').write_text('\n'.join(log), encoding='utf-8')
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
    objects = []
    for p in sorted(src.glob('*.c')):
        obj = out / (p.stem + '.o')
        run([gcc, *flags, f'-O{args.opt}', '-g3', '-Wall', '-I' + str(bsp / 'include'), '-I' + str(src), *defines, '-c', p, '-o', obj])
        objects.append(obj)
    elf = out / 'cdc_bench.elf'
    spec = original.parent / 'Debug/Xilinx.spec'
    run([gcc, *flags, '-specs=' + str(spec), '-Wl,-build-id=none', '-Wl,-T,' + str(src / 'lscript.ld'),
         '-Wl,-Map,' + str(out / 'cdc_bench.map'), '-L' + str(bsp / 'lib'), '-o', elf, *objects,
         '-Wl,--start-group', '-lxil', '-lgcc', '-lc', '-Wl,--end-group'])
    manifest['elf_sha256'] = hashlib.sha256(elf.read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(elf)


if __name__ == '__main__':
    main()
