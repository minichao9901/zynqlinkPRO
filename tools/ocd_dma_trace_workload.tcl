init
reset halt
source tools/f103_clock64.tcl
for {set i 0} {$i < 3} {incr i} {
    dump_image results/optimization/trace_read.bin 0x20000000 0x5000
}
shutdown
