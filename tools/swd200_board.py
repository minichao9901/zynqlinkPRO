"""Cable-bound J7 SelectIO loading and physical OCM verification."""

import json
from pathlib import Path
import re
import sys

from probe_flash import Session, sha
from swd200 import ROOT, RTL
from verify_probe_ocm_code import read_ocm_code
from zynq_memory import PhysicalMemory

sys.path.insert(0, str(ROOT / "etm-service/tools"))
from probe_ownership import Ownership
sys.path.remove(str(ROOT / "etm-service/tools"))

SDK = Path("E:/Xilinx/SDK/2018.3")
PAIR = ROOT / "prebuilt/swd-only-200mhz-pipeline-20261118"
ID = 0x53323030
BOARD_TCL = (RTL / "board.tcl").read_text(encoding="ascii")


def record(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class Board:
    def __init__(self, folder, cable):
        if not re.fullmatch(r"[0-9]+", cable):
            raise ValueError("Specify the Digilent cable serial")
        folder.mkdir(parents=True, exist_ok=False)
        self.folder = folder
        self.session = Session(folder, SDK, "tcp:127.0.0.1:3121", cable_serial=cable)
        self.memory = PhysicalMemory(self.session, cable_serial=cable)
        self.cable = cable
        self.select = f' && jtag_cable_serial == "{cable}"'

    def tcl(self, body):
        return self.memory.run(BOARD_TCL + "\n" + body)

    def load(self, files, *, experimental):
        bit, elf, init = (p.resolve() for p in files)
        # Never select or reset a Zynq on another cable.
        if self.memory.read_words(0xf8000530)[0] & 0x0fffffff != 0x03727093:
            raise RuntimeError("Expected XC7Z020 PS identity")
        blob, _, sections = read_ocm_code(elf)
        select = self.select
        mailbox_clear = "mwr -force 0x2ff00 0\n" if experimental else ""
        self.session.run(f'''targets -set -filter {{name =~ "APU"{select}}}
rst -system
after 1000
set ready 0
for {{set n 0}} {{$n < 50}} {{incr n}} {{
    if {{![catch {{
        targets -set -filter {{name =~ "APU"{select}}}
        mrd -force -value 0xf8007080
    }} reason]}} {{set ready 1; break}}
    after 100
}}
if {{!$ready}} {{error "APU did not recover: $reason"}}
source {{{init.as_posix()}}}
ps7_init
targets -set -filter {{name =~ "xc7z020"{select}}}
fpga -f {{{bit.as_posix()}}}
after 300
targets -set -filter {{name =~ "APU"{select}}}
ps7_post_config
targets -set -filter {{name =~ "ARM Cortex-A9 MPCore #0*"{select}}}
rst -processor
configparams force-mem-access 1
dow {{{elf.as_posix()}}}
{mailbox_clear}con''')
        image = (self.folder / ("swd-code.bin" if experimental else "original-code.bin")).resolve()
        limit = max(section[3] + section[5] for section in sections)
        checks = f"""
swd_wait 0x2ff00 0xffffffff {ID}
swd_wait 0x40000000 0xffffffff {ID}
swd_wait 0x40000004 33 33
if {{[swd_rd 0x2ff18]}} {{error "SWD clock startup error"}}
""" if experimental else ""
        self.tcl(checks + f"physrd -force -bin -file {{{image.as_posix()}}} 0 {(limit + 3)//4}")
        live = image.read_bytes()
        for section in sections:
            address, offset, count = section[3:6]
            if live[address:address + count] != blob[offset:offset + count]:
                raise RuntimeError("Physical MEM-AP0 executable mismatch")
        result = dict(cable=self.cable, sha256={k: sha(p) for k, p in
                      zip(("bit", "elf", "ps_init"), (bit, elf, init))},
                      live_code_bytes=sum(section[5] for section in sections))
        record(self.folder / ("load-swd.json" if experimental else "load-original.json"), result)
        return result


def candidate(pair=PAIR):
    hashes = json.loads((pair / "manifest.json").read_text())["sha256"]
    for name, digest in hashes.items():
        if sha(pair / name) != digest:
            raise RuntimeError(f"Candidate SHA-256 differs for {name}")
    return tuple(pair / name for name in ("probe.bit", "application.elf", "ps7_init.tcl"))
