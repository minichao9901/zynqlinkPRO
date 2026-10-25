"""Final bring-up check: three fresh OpenOCD sessions against the DAPLink."""
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(r"E:\zynqlinkPRO")
SCRIPTS = Path(r"E:\Share\env-windows\rtt-debugger-support-package-0.4.0\bin\scripts")

TCL = r"""
init
reset halt
dump_image results/daplink/sram/final_flash.bin 0x08000000 0x8000
load_image results/daplink/sram/pat_20480.bin 0x20000000
dump_image results/daplink/sram/final_sram.bin 0x20000000 0x5000
echo "SESSION_DONE"
exit
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    tcl = ROOT / "build" / "final_check.tcl"
    tcl.write_text(TCL, encoding="utf-8")
    pat = sha(ROOT / "results/daplink/sram/pat_20480.bin")
    rows = []
    for i in range(3):
        t0 = time.time()
        p = subprocess.run(
            ["openocd", "-s", str(SCRIPTS), "-f", str(ROOT / "tools/openocd_dap.cfg"),
             "-d1", "-c", f"script {tcl.as_posix()}"],
            cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=120)
        elapsed = time.time() - t0
        ok = "SESSION_DONE" in (p.stdout + p.stderr)
        sram = sha(ROOT / "results/daplink/sram/final_sram.bin") if (ROOT / "results/daplink/sram/final_sram.bin").exists() else ""
        rows.append({"run": i, "session_ok": ok, "sram_match": sram == pat,
                     "wall_seconds": round(elapsed, 2),
                     "errors": [l for l in (p.stdout + p.stderr).splitlines() if "Error" in l][:3]})
        time.sleep(0.5)
    print(json.dumps(rows, indent=2))
    (ROOT / "results/daplink/final_check.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
