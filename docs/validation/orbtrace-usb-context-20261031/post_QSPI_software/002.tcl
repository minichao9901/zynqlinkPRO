connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
mrd -force -bin -file {E:/zynqlinkPRO_orbtrace_opt/build/qspi_boot/fixed_USB_code_1.bin} 0 17817
puts CODE_READ
disconnect
exit
