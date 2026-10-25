init
reset halt
echo "PC=[reg pc]"
load_image results/daplink/sram/pat_20480.bin 0x20000000
verify_image results/daplink/sram/pat_20480.bin 0x20000000
echo "VERIFY_OK"
dump_image results/daplink/sram/reset_dump.bin 0x20000000 0x5000
echo "DUMP_OK"
exit
