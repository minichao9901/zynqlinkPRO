init
reset halt
load_image results/daplink/sram/pat_20480.bin 0x20000000
for {set i 0} {$i < 8} {incr i} {
    set t0 [clock milliseconds]
    dump_image results/daplink/sram/t_$i.bin 0x20000000 0x5000
    set t1 [clock milliseconds]
    echo "DUMP $i ms=[expr {$t1-$t0}]"
}
for {set i 0} {$i < 8} {incr i} {
    set t0 [clock milliseconds]
    load_image results/daplink/sram/pat_20480.bin 0x20000000
    set t1 [clock milliseconds]
    echo "LOAD $i ms=[expr {$t1-$t0}]"
}
exit
