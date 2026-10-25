init
reset halt
load_image results/daplink/sram/pat_20480.bin 0x20000000
echo "M1=[mdw 0x20000000 2]"
echo "P1=[reg pc] D1=[mdw 0xE000EDF0 1]"
if {[catch {verify_image results/daplink/sram/pat_20480.bin 0x20000000} e]} {
    echo "VERIFY_FAIL"
}
echo "M2=[mdw 0x20000000 2]"
echo "P2=[reg pc] D2=[mdw 0xE000EDF0 1]"
echo "RCC_CSR=[mdw 0x40021024 1]"
exit
