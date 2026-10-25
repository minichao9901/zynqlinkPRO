init
reset halt
for {set i 0} {$i < 150} {incr i} {
    dump_image results/daplink/sram/loop_dump.bin 0x20000000 0x5000
}
echo "LOOP_DONE"
exit
