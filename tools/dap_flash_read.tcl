init
reset halt
for {set i 0} {$i < 3} {incr i} {
    set t0 [clock milliseconds]
    dump_image results/daplink/sram/flash_$i.bin 0x08000000 0x20000
    set t1 [clock milliseconds]
    echo "FLASH_DUMP $i ms=[expr {$t1-$t0}]"
}
exit
