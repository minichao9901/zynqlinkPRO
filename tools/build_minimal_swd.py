"""Build only the standalone Zynq SWD fixture ELF (bit: minimal_swd/build.tcl)."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/minimal_swd';OUT.mkdir(parents=True,exist_ok=True)
GCC=Path('E:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe')
BSP=ROOT/'reference/legacy_zynq/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0'
SRC=ROOT/'firmware/diagnostics/minimal_swd_zynq.c'
support=ROOT/'firmware/xusbps_daplink_dma'
elf=OUT/'minimal_swd.elf'
cmd=[GCC,'-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-O2','-g','-Wall','-Wextra',
 '-I',BSP/'include','-specs='+str(support/'Xilinx.spec'),'-Wl,-build-id=none',
 '-Wl,-T,'+str(support/'lscript.ld'),'-L'+str(BSP/'lib'),SRC,'-o',elf,
 '-Wl,--start-group','-lxil','-lgcc','-lc','-Wl,--end-group']
r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True)
(OUT/'firmware_build.log').write_text(r.stdout+r.stderr)
assert r.returncode==0,r.stdout+r.stderr
nm=subprocess.check_output([str(GCC.with_name('arm-none-eabi-nm.exe')),str(elf)],text=True)
address=int(re.search(r'^([0-9a-fA-F]+) [A-Za-z] swd_diag$',nm,re.M)[1],16)
(OUT/'firmware.json').write_text(json.dumps(dict(mailbox_address=address,
 elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
 source_sha256=hashlib.sha256(SRC.read_bytes()).hexdigest(),command=list(map(str,cmd))),indent=2))
print(elf,'mailbox',hex(address))
