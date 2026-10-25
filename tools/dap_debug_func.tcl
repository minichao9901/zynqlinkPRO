init
reset halt
echo "PC0=[reg pc]"
for {set i 0} {$i < 5} {incr i} {
    step
    echo "STEP $i PC=[reg pc]"
}
echo "FLASH=[flash probe 0]"
echo "BP=[bp 0x08000180 2 hw]"
resume
after 200
halt
echo "AFTER_BP PC=[reg pc]"
rbp 0x08000180
exit
