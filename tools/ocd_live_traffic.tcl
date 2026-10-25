init
reset halt
set end [expr {[clock seconds] + 900}]
set n 0
while {[clock seconds] < $end} {
    dump_image results/daplink/sram/live_dump.bin 0x20000000 0x4000
    incr n
}
echo "LIVE_DONE $n"
exit
