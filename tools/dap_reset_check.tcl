init
reset halt
echo "PC_AFTER_RESET=[reg pc]"
echo "DHCSR=[mdw 0xE000EDF0 1]"
echo "DMA_CCR1=[mdw 0x40020008 1]"
echo "DMA_CCR2=[mdw 0x40020408 1]"
echo "DMA_CCR3=[mdw 0x40020808 1]"
echo "DMA_CCR4=[mdw 0x40020C08 1]"
echo "DMA_CCR5=[mdw 0x40021008 1]"
echo "DMA_CCR6=[mdw 0x40021408 1]"
echo "DMA_CCR7=[mdw 0x40021808 1]"
for {set i 0} {$i < 16} {incr i} {
    mww [expr {0x20000000 + $i * 4}] 0xA5A5A5A5
}
echo "W1=[mdw 0x20000000 8]"
sleep 500
echo "W2=[mdw 0x20000000 8]"
exit
