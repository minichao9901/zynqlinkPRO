init
reset halt
source tools/f103_clock64.tcl
echo [mdw 0x40021000 2]
set base 0x20000000
set size 0x5000
set pat results/daplink/sram/pat_20480.bin
load_image $pat $base
set t0 [clock milliseconds]
for {set i 0} {$i < 50} {incr i} {dump_image results/daplink/sram/clock64_read.bin $base $size}
set t1 [clock milliseconds]
for {set i 0} {$i < 50} {incr i} {load_image $pat $base}
set t2 [clock milliseconds]
dump_image results/daplink/sram/clock64_final.bin $base $size
echo "CLOCK64 READ50_ms=[expr {$t1-$t0}] WRITE50_ms=[expr {$t2-$t1}]"
shutdown
