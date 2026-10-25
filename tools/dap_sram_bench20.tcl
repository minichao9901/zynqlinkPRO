set base 0x20000000
set size 0x5000
set pat results/daplink/sram/pat_20480.bin
set out results/daplink/sram/bench_out.bin

init
reset halt
echo "PC=[reg pc]"
load_image $pat $base
dump_image results/daplink/sram/bench_check.bin $base $size
echo "CHECK_DUMP_DONE"

set t0 [clock milliseconds]
for {set i 0} {$i < 20} {incr i} {
    dump_image $out $base $size
}
set t1 [clock milliseconds]
echo "READ20 ms=[expr {$t1-$t0}]"

set t2 [clock milliseconds]
for {set i 0} {$i < 20} {incr i} {
    load_image $pat $base
}
set t3 [clock milliseconds]
echo "WRITE20 ms=[expr {$t3-$t2}]"

dump_image results/daplink/sram/bench_final.bin $base $size
echo "FINAL_DUMP_DONE"
exit
