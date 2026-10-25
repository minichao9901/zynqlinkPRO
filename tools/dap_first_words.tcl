init
halt
for {set i 0} {$i < 16} {incr i} {
    mww [expr {0x20000000 + $i * 4}] 0xA5A5A5A5
}
echo "BEFORE=[mdw 0x20000000 16]"
load_image results/daplink/sram/pat_20480.bin 0x20000000
echo "AFTER=[mdw 0x20000000 16]"
echo "TAIL=[mdw 0x20004FF0 4]"
exit
