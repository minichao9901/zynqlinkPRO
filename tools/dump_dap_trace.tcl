connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
mrd -bin -file E:/zynqlinkPRO/results/daplink/dap_trace.bin 0x3F000000 16388
disconnect
exit
