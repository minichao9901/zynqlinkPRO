connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
mrd -force -bin -file {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-boot-failure-20261101/cmd-source.bin} 0x12ab00 1024
mrd -force -bin -file {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-boot-failure-20261101/rsp-destination.bin} 0x12bb00 1024
mrd -force -bin -file {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-boot-failure-20261101/cmd-bram.bin} 0x42000000 1024

disconnect
exit
