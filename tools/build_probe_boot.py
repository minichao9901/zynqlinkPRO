"""Build a DDR-resident second-stage FSBL so an OCM-linked probe can boot.

Stage zero initializes DDR and copies the embedded loader there. The SDK FSBL
then configures PL and loads the application at OCM zero without overwriting
itself. A conventional forced-JTAG FSBL is built for program_flash recovery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess


def loads(elf):
    data = Path(elf).read_bytes()
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    if h[0][:6] != b'\x7fELF\x01\x01':
        raise ValueError('Expected little-endian ELF32')
    rows = []
    for i in range(h[10]):
        p = struct.unpack_from('<IIIIIIII', data, h[5] + i*h[9])
        if p[0] == 1:
            rows.append(dict(address=p[3], file_bytes=p[4], memory_bytes=p[5], flags=p[6]))
    return h[4], rows


def partitions(path):
    data = Path(path).read_bytes()
    assert struct.unpack_from('<II', data, 0x20) == (0xaa995566, 0x584c4e58)
    offset = struct.unpack_from('<I', data, 0x9c)[0]
    rows = []
    for i in range(32):
        p = struct.unpack_from('<16I', data, offset+64*i)
        assert sum(p) & 0xffffffff == 0xffffffff, 'Partition header checksum'
        if not p[0]:
            break
        start, length = p[5]*4, p[1]*4
        assert start+length <= len(data)
        if p[6] & 0x7000:
            assert p[6]&0x7000 == 0x1000, 'Expected MD5 partition checksum'
            assert hashlib.md5(data[start:start+length]).digest() == data[p[8]*4:p[8]*4+16]
        rows.append(dict(load_address=p[3], entry=p[4], offset=start, bytes=length, attributes=p[6]))
    assert len(rows) == 3 and rows[0]['load_address']==0 and rows[2]['load_address']==0
    assert rows[1]['attributes']&0x20 and rows[2]['attributes']&0x10
    return rows


def patched_sources(vendor, out):
    out.mkdir(parents=True, exist_ok=True)
    for p in vendor.iterdir():
        if p.is_file():
            shutil.copyfile(p, out/p.name)
    p = out/'main.c'
    s = p.read_text()
    marker = 'int main(void)'
    assert s.count(marker) == 1
    s = s.replace(marker, 'u32 ProbePsPartitionSeen = 0;\n'+marker)
    marker = '\tStatus = ps7_init();'
    assert s.count(marker) == 1
    s = s.replace(marker, '''#ifdef PROBE_DDR_STAGE2
    Status = XST_SUCCESS;
    ((volatile u32 *)0x03FF0000U)[5] = 2;
#else
''' + marker + '\n#endif')
    marker = '\tBootModeRegister &= BOOT_MODES_MASK;'
    assert s.count(marker) == 2
    s = s.replace(marker, marker + '''
#ifdef PROBE_PROGRAMMER_FSBL
    /* Keep the programming init loader in JTAG mode even with QSPI straps. */
    BootModeRegister = JTAG_MODE;
#endif
#ifdef PROBE_DDR_STAGE2
    ((volatile u32 *)0x03FF0000U)[3] = BootModeRegister;
#endif
''', 1)
    marker = 'if(FsblStartAddr == 0) {'
    assert s.count(marker) == 1
    s = s.replace(marker, '''#ifdef PROBE_DDR_STAGE2
    ((volatile u32 *)0x03FF0000U)[5] = 0x600;
    ((volatile u32 *)0x03FF0000U)[6] = FsblStartAddr;
    ((volatile u32 *)0x03FF0000U)[7] = ProbePsPartitionSeen;
#endif
    if(FsblStartAddr == 0 && !ProbePsPartitionSeen) {''')
    p.write_text(s)
    p = out/'image_mover.c'
    s = p.read_text()
    begin = s.index('\t\tif ((PSPartitionFlag == 1) && (PartitionLoadAddr < DDR_START_ADDR))')
    end = s.index('\n\t\tif (PSPartitionFlag && (PartitionLoadAddr > DDR_END_ADDR))', begin)
    original = s[begin:end]
    replacement = '''#ifdef PROBE_DDR_STAGE2
        /* The loader is executing in DDR, so unsigned OCM images are safe. */
        if (PSPartitionFlag && PartitionLoadAddr < DDR_START_ADDR) {
            u64 limit = (u64)PartitionLoadAddr + ((u64)PartitionImageLength << 2);
            if (limit > 0x00030000U || SignedPartitionFlag || EncryptedPartitionFlag) {
                OutputStatus(INVALID_LOAD_ADDRESS_FAIL); FsblFallback();
            }
        }
        if (PSPartitionFlag && PartitionLoadAddr < 0x02200000U &&
            (u64)PartitionLoadAddr + ((u64)PartitionImageLength << 2) > 0x02000000U) {
            OutputStatus(INVALID_LOAD_ADDRESS_FAIL); FsblFallback();
        }
#else
''' + original + '\n#endif\n'
    s = s[:begin]+replacement+s[end:]
    marker = 'ExecAddress = PartitionExecAddr;'
    assert s.count(marker) == 1
    s = s.replace(marker, marker+'\n            ProbePsPartitionSeen = 1;')
    s = s.replace('u32 ExecutionAddress;', 'u32 ExecutionAddress;\nextern u32 ProbePsPartitionSeen;')
    p.write_text(s)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bsp', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path('build/qspi_boot/loader'))
    p.add_argument('--sdk', type=Path, default=Path('E:/Xilinx/SDK/2018.3'))
    p.add_argument('--bit', type=Path)
    p.add_argument('--elf', type=Path)
    a = p.parse_args()
    if bool(a.bit) != bool(a.elf):
        p.error('--bit and --elf must be paired')
    root = Path(__file__).resolve().parents[1]
    boot = root/'firmware/boot'
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    bsp = a.bsp.resolve()
    if (bsp/'ps7_cortexa9_0').is_dir():
        bsp = bsp/'ps7_cortexa9_0'
    gcc = a.sdk/'gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
    objcopy = gcc.with_name('arm-none-eabi-objcopy.exe')
    src = out/'src'; patched_sources(boot/'vendor_fsbl_2018_3', src)
    for name in ['ps7_init.c', 'ps7_init.h']:
        shutil.copyfile(boot/'hardware'/name, src/name)
    logs = []

    def run(cmd):
        result = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, errors='replace')
        logs.append(subprocess.list2cmdline(list(map(str, cmd)))+'\n'+result.stdout+result.stderr)
        (out/'build.log').write_text('\n'.join(logs))
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)

    base = ['-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard', '-Os', '-g',
            '-Wno-builtin-macro-redefined', '-D__DATE__="Oct 31 2026"', '-D__TIME__="00:00:00"',
            '-ffunction-sections', '-fdata-sections', '-DSDK_RELEASE_YEAR=2018',
            '-DSDK_RELEASE_QUARTER=3', '-DFSBL_DEBUG', '-I'+str(src), '-I'+str(bsp/'include')]
    original_linker = (src/'lscript.ld').read_text()
    (out/'stage0.ld').write_text(original_linker)
    linker = original_linker.replace('ORIGIN = 0x00000000, LENGTH = 0x00030000',
                                    'ORIGIN = 0x02000000, LENGTH = 0x00100000')
    linker = linker.replace('ORIGIN = 0xFFFF0000, LENGTH = 0x0000FE00',
                            'ORIGIN = 0x02100000, LENGTH = 0x00010000')
    (out/'stage2.ld').write_text(linker)
    specs = root/'firmware/xusbps_daplink_dma/Xilinx.spec'

    def compile_link(name, sources, defines, script):
        objects = []
        target = out/name; target.mkdir(exist_ok=True)
        for source in sources:
            obj = target/(source.stem+'.o')
            run([gcc, *base, *defines, '-c', source, '-o', obj])
            objects.append(obj)
        elf = out/(name+'.elf')
        run([gcc, *base, '-specs='+str(specs), '-Wl,-build-id=none', '-Wl,--gc-sections',
             '-Wl,-T,'+str(script), '-Wl,-Map,'+str(out/(name+'.map')),
             '-L'+str(bsp/'lib'), '-o', elf, *objects,
             '-Wl,--start-group', '-lxil', '-lgcc', '-lc', '-Wl,--end-group'])
        return elf

    fsbl_sources = sorted(p for p in src.glob('*.c') if not p.name.startswith('reader_'))+[src/'fsbl_handoff.S']
    stage2 = compile_link('fsbl_stage2', fsbl_sources, ['-DPROBE_DDR_STAGE2=1'], out/'stage2.ld')
    run([objcopy, '-O', 'binary', stage2, out/'fsbl_stage2.bin'])
    asm = out/'embedded_stage2.S'
    asm.write_text('.section .rodata.probe_stage2,"a"\n.balign 64\n.global probe_stage2_start\n'
                   'probe_stage2_start:\n.incbin "'+str(out/'fsbl_stage2.bin').replace('\\','/')+'"\n'
                   '.global probe_stage2_end\nprobe_stage2_end:\n')
    stage0 = compile_link('fsbl_stage0', [boot/'stage0.c', src/'ps7_init.c', src/'fsbl_handoff.S', asm],
                          [], out/'stage0.ld')
    programmer = compile_link('fsbl_programmer', fsbl_sources, ['-DPROBE_PROGRAMMER_FSBL=1'], out/'stage0.ld')
    reader_linker = linker.replace('0x02000000', '0x03000000').replace('0x02100000', '0x03100000')
    (out/'reader.ld').write_text(reader_linker)
    # SDK 2018.3's generic opcode path pads RX for a 5-byte header. Register
    # Winbond's dedicated 4-byte-address read as a four-byte initial TX word;
    # its fifth address byte then travels through the normal data FIFO.
    driver = boot/'vendor_qspips_2018_3/xqspips.c'
    reader_driver = src/'reader_xqspips.c'
    reader_driver.write_text(driver.read_text().replace(
        'static XQspiPsInstFormat FlashInst[] = {',
        'static XQspiPsInstFormat FlashInst[] = {\n {0x13, 4, XQSPIPS_TXD_00_OFFSET},'))
    compile_link('qspi_read', [boot/'qspi_read.c', reader_driver], [], out/'reader.ld')
    for elf, lo, hi in [(stage0, 0, 0x30000), (programmer, 0, 0x30000),
                        (stage2, 0x02000000, 0x02200000)]:
        entry, segments = loads(elf)
        assert all(lo <= s['address'] and s['address']+s['file_bytes'] <= hi
                   for s in segments if s['file_bytes']), (elf, segments)
    if a.bit:
        entry, segments = loads(a.elf)
        for segment in segments:
            if not segment['file_bytes']:
                continue
            start, end = segment['address'], segment['address']+segment['file_bytes']
            assert not (start < 0x02200000 and end > 0x02000000), 'App overlaps DDR loader'
        bif = out/'BOOT.bif'
        bif.write_text('the_ROM_image:\n{\n [bootloader] "'+str(stage0).replace('\\','/')+'"\n'
                       ' [checksum=md5] "'+str(a.bit.resolve()).replace('\\','/')+'"\n'
                       ' [checksum=md5] "'+str(a.elf.resolve()).replace('\\','/')+'"\n}\n')
        run([a.sdk/'bin/bootgen.bat', '-arch', 'zynq', '-image', bif, '-o', out/'BOOT.bin', '-w', 'on'])
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(architecture='OCM stage0 -> DDR32MiB stage2 -> PL + OCM application',
                    stage2_reserved=[0x02000000, 0x02200000], trace_address=0x03FF0000,
                    source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
                    compiler_flags=base, bsp_sha256=sha(bsp/'lib/libxil.a'),
                    source_sha256={str(path.relative_to(root)):sha(path) for path in boot.rglob('*') if path.is_file()},
                    compiled_source_sha256={path.name:sha(path) for path in src.iterdir() if path.is_file()},
                    files={path.name:sha(path) for path in out.iterdir() if path.is_file() and path.suffix in ['.elf','.bin','.bif']},
                    boot_validation='not yet performed')
    if a.bit:
        manifest['input_pair'] = {'bit_sha256': sha(a.bit), 'elf_sha256': sha(a.elf)}
        manifest['boot_partitions'] = partitions(out/'BOOT.bin')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest['files'],indent=2))


if __name__ == '__main__':
    main()

