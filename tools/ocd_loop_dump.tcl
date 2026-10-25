init
reset halt
load_image results/daplink/sram/pat_20480.bin 0x20000000
for {set i 0} {$i < 25} {incr i} {
    dump_image results/daplink/sram/loop_dump.bin 0x20000000 0x5000
    after 100
}
echo "LOOP_DONE"
exit
