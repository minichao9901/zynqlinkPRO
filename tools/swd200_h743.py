"""H743-only SelectIO bring-up and recovery."""
import argparse
from swd200_board import Board, Ownership, Path, ROOT, candidate

RELEASE = ROOT / "prebuilt/release-20261106"
ORIGINAL = (
    RELEASE / "probe.bit",
    ROOT / "prebuilt/h743-jtag66-20261109/application.elf",
    RELEASE / "ps7_init.tcl",
)
BASE = 0x24050000

H743_TCL = 'proc swd_ident {} {\n    # Repeat read transactions within a batch, including DP parity checking.\n    set reply [swd_batch {16 0 2 0 2 0 2 0 2 0 2 0}]\n    set passed [expr {([lindex $reply 0] & 0xffff) == 6}]\n    foreach id [lrange $reply 2 end] {\n        if {$id != 0x6ba02477} { set passed 0 }\n    }\n    return [linsert $reply 0 $passed]\n}\n\nproc swd_ap_setup {} {\n    swd_require {16 0}\n    if {[lindex [swd_require {2 0}] 0] != 0x6ba02477} { error "H743 DPIDR mismatch" }\n    swd_require {0 0x1e 4 0x50000000 8 0}\n    for {set n 0} {$n < 32} {incr n} {\n        set state [lindex [swd_require {6 0}] 0]\n        if {($state & 0xa0000000) == 0xa0000000} { break }\n    }\n    if {($state & 0xa0000000) != 0xa0000000} { error "DP power handshake failed" }\n    swd_require {1 0x23000052}\n    set id [lindex [swd_require {5 0x5c001000 15 0 14 0}] 2]\n    if {$id != 0x20036450} { error [format "H743 device mismatch: %08x" $id] }\n    swd_require {5 0x24050000}\n}\n'

def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("identify", "restore"))
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--cable", required=True)
    cli.add_argument("--execute", action="store_true")
    args = cli.parse_args()
    files = candidate()
    if not args.execute:
        print(f"{args.action}: HS3 {args.cable}, H743 {BASE:#x}, SWD. Use --execute for the board.")
        return
    device = Board(args.out, args.cable)
    lease = Ownership()
    try:
        if args.action == "restore":
            print(device.load(ORIGINAL, experimental=False))
        else:
            from probe_load import check_streams, probe_state

            check_streams()
            probe_state(device.session, cable_serial=args.cable)
            print(device.load(files, experimental=True), flush=True)
            result = device.tcl(H743_TCL + """
puts "CLOCK [swd_config 0 0 12 12 2]"
puts "IDENT [swd_ident]"
""")
            print(result)
    finally:
        lease.close()


if __name__ == "__main__":
    main()
