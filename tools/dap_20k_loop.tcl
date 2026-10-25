init
halt
for {set i 0} {$i < 3} {incr i} {
    load_image results/daplink/sram/pat_20480.bin 0x20000000
    dump_image results/daplink/sram/d_$i.bin 0x20000000 0x5000
    echo "ITER $i [mdw 0x20000000 2]"
}
exit
