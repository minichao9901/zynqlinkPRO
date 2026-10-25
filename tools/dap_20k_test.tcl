init
halt
echo "FLASH_SIZE_REG=[mdw 0x1FFFF7E0 1]"
load_image results/daplink/sram/pat_20480.bin 0x20000000
verify_image results/daplink/sram/pat_20480.bin 0x20000000
echo "VERIFY_DONE"
dump_image results/daplink/sram/dump_20480.bin 0x20000000 0x5000
echo "DUMP_DONE"
exit
