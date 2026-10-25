init
reset halt
for {set i 0} {$i < 3} {incr i} {
    dump_image results/daplink/sram/trace_dump.bin 0x20000000 0x5000
    after 100
}
echo "TRACE_WORKLOAD_DONE"
exit
