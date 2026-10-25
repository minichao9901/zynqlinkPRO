init
reset halt
mww 0x20000000 0x12345678
echo "MW=[mdw 0x20000000 1]"
foreach n {64 256 512 1024 4096 8192 20480} {
    set f results/daplink/sram/pat_$n.bin
    if {[catch {
        load_image $f 0x20000000
        verify_image $f 0x20000000
    } e]} {
        echo "SIZE $n FAIL $e"
    } else {
        echo "SIZE $n OK [mdw 0x20000000 1]"
    }
}
exit
