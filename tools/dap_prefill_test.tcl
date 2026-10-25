init
halt
for {set i 0} {$i < 32} {incr i} {
    mww [expr {0x20000000 + $i * 4}] 0xA5A5A5A5
}
dump_image results/daplink/sram/pre.bin 0x20000000 0x100
load_image results/daplink/sram/pat_20480.bin 0x20000000
dump_image results/daplink/sram/post.bin 0x20000000 0x100
echo "PRE=[mdw 0x20000000 16]"
echo "POST=[mdw 0x20000000 16]"
exit
