init
reset halt
source tools/f103_clock64.tcl
set end [expr {[clock milliseconds]+12000}]
while {[clock milliseconds] < $end} {
    dump_image results/optimization/la_traffic.bin 0x20000000 0x5000
}
shutdown
