connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
mrd -force -bin -file {E:/zynqlinkPRO_qspi_cli/build/qspi_cli_verify_cpu_reset/programmed_readback.bin} 0x04000000 1066164
puts READ_COMPLETE
disconnect
exit
