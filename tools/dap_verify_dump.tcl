init
reset halt
load_image results/daplink/sram/pat_20480.bin 0x20000000
dump_image results/daplink/sram/v1.bin 0x20000000 0x5000
echo "D1=[mdw 0x20000000 2]"
if {[catch {verify_image results/daplink/sram/pat_20480.bin 0x20000000} e]} {
    echo "VERIFY_FAIL"
}
dump_image results/daplink/sram/v2.bin 0x20000000 0x5000
echo "D2=[mdw 0x20000000 2]"
exit
