init
reset halt
mww 0x20000000 0xDEADBEEF
echo "A=[mdw 0x20000000 1]"
load_image results/daplink/sram/pat_64.bin 0x20001000
echo "B=[mdw 0x20000000 1] [mdw 0x20001000 1]"
verify_image results/daplink/sram/pat_64.bin 0x20001000
echo "VERIFY_10_OK"
load_image results/daplink/sram/pat_64.bin 0x20000000
echo "C=[mdw 0x20000000 1]"
exit
