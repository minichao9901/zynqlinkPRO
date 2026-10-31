connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
source {E:/zynqlinkPRO_orbtrace_opt/prebuilt/20261031_orbtrace_opt_qspi_usbfix_7020_120/ps7_init.tcl}
ps7_init
dow {E:/zynqlinkPRO_orbtrace_opt/prebuilt/20261031_orbtrace_opt_qspi_usbfix_7020_120/qspi_read.elf}
disconnect
exit
