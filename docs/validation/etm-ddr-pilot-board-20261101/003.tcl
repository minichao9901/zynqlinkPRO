connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
mrd -force -bin -file {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-boot-failure-20261101/cmd-source-actual.bin} 0x12cb40 1024
mwr -force 0x40020004 0x7000
mwr -force 0x40020018 0x42000000
mwr -force 0x40020020 0x10001000
mwr -force 0x40020028 4
after 10
puts "CDMA_CASE 4 [mrd -force -value 0x40020004] [mrd -force -value 0x10001000 1]"
mwr -force 0x40020004 0x7000
mwr -force 0x40020018 0x42000000
mwr -force 0x40020020 0x10001400
mwr -force 0x40020028 8
after 10
puts "CDMA_CASE 8 [mrd -force -value 0x40020004] [mrd -force -value 0x10001400 2]"
mwr -force 0x40020004 0x7000
mwr -force 0x40020018 0x42000000
mwr -force 0x40020020 0x10001800
mwr -force 0x40020028 16
after 10
puts "CDMA_CASE 16 [mrd -force -value 0x40020004] [mrd -force -value 0x10001800 4]"
mwr -force 0x40020004 0x7000
mwr -force 0x40020018 0x42000000
mwr -force 0x40020020 0x10001c00
mwr -force 0x40020028 64
after 10
puts "CDMA_CASE 64 [mrd -force -value 0x40020004] [mrd -force -value 0x10001c00 16]"
mwr -force 0x40020004 0x7000
mwr -force 0x40020018 0x42000000
mwr -force 0x40020020 0x10002000
mwr -force 0x40020028 256
after 10
puts "CDMA_CASE 256 [mrd -force -value 0x40020004] [mrd -force -value 0x10002000 64]"

disconnect
exit
