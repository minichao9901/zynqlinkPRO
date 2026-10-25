init
reset halt
load_image results/daplink/sram/pat_20480.bin 0x20000000
echo "M1=[mdw 0x20000000 4]"
if {[catch {verify_image results/daplink/sram/pat_20480.bin 0x20000000} e]} {
    echo "VERIFY_FAIL $e"
} else {
    echo "VERIFY_OK"
}
echo "M2=[mdw 0x20000000 4]"
exit
