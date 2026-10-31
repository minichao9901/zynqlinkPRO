connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
puts "PC [rrd pc]"
puts "R0 [rrd r0]"
puts "CDMA [mrd -force -value 0x40020000 12]"
puts "DMA_STATUS [mrd -force -value 0x12cb30 4]"
puts "SWD [mrd -force -value 0x40010000 4]"
puts "DDR_PILOT [mrd -force -value 0x40040000 16]"
puts "CLOCK [mrd -force -value 0xf8000170 1]"

disconnect
exit
