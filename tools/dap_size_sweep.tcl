init
halt
foreach n {64 256 512 1024 4096 20480} {
    set f results/daplink/sram/pat_$n.bin
    if {[catch {
        load_image $f 0x20001000
        verify_image $f 0x20001000
    } e]} {
        echo "SIZE $n FAIL $e"
    } else {
        echo "SIZE $n OK"
    }
}
exit
