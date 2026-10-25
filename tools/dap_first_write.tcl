init
reset halt
load_image results/daplink/sram/pat_64.bin 0x20000000
echo "AFTER1=[mdw 0x20000000 1]"
load_image results/daplink/sram/pat_64.bin 0x20000000
echo "AFTER2=[mdw 0x20000000 1]"
mww 0x20000000 0xCAFEBABE
echo "AFTER3=[mdw 0x20000000 1]"
load_image results/daplink/sram/pat_64.bin 0x20000000
echo "AFTER4=[mdw 0x20000000 1]"
exit
