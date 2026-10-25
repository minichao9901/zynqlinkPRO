connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "count=[mrd 0x3F000000 1]"
puts "hz=[mrd 0x3F000004 1]"
mrd -bin -file E:/zynqlinkPRO/results/daplink/trace_test.bin 0x3F000040 16
disconnect
exit
