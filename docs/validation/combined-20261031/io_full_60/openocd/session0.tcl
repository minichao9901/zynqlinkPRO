
init
halt

dump_image E:/zynqlinkPRO_combined_verify/docs/validation/combined-20261031/io_full_60/openocd/session0.backup.bin 0x20000000 0x5000
adapter speed 60000
set bench_error [catch {
load_image E:/zynqlinkPRO_combined_verify/docs/validation/combined-20261031/io_full_60/openocd/pattern.bin 0x20000000
set t0 [clock milliseconds]
for {set i 0} {$i < 30} {incr i} {dump_image E:/zynqlinkPRO_combined_verify/docs/validation/combined-20261031/io_full_60/openocd/session0.read.bin 0x20000000 0x5000}
set t1 [clock milliseconds]
for {set i 0} {$i < 30} {incr i} {load_image E:/zynqlinkPRO_combined_verify/docs/validation/combined-20261031/io_full_60/openocd/pattern.bin 0x20000000}
set t2 [clock milliseconds]
dump_image E:/zynqlinkPRO_combined_verify/docs/validation/combined-20261031/io_full_60/openocd/session0.written.bin 0x20000000 0x5000
echo "MEASURE read_ms=[expr {$t1-$t0}] write_ms=[expr {$t2-$t1}]"
} bench_message]
adapter speed 50000
load_image E:/zynqlinkPRO_combined_verify/docs/validation/combined-20261031/io_full_60/openocd/session0.backup.bin 0x20000000
dump_image E:/zynqlinkPRO_combined_verify/docs/validation/combined-20261031/io_full_60/openocd/session0.restored.bin 0x20000000 0x5000
if {$bench_error} {error $bench_message}
echo "BENCH_COMPLETE"
shutdown
