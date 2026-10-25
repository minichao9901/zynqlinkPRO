init
reset halt
echo "PC0=[reg pc]"
load_image results/daplink/sram/pat_64.bin 0x20000000
echo "M=[mdw 0x20000000 4]"
echo "PC1=[reg pc]"
echo "DHCSR=[mdw 0xE000EDF0 1]"
echo "DBGMCU_CR=[mdw 0xE0042004 1]"
exit
