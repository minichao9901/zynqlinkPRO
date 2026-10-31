connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
puts "RESTORED_PC [rrd pc]"
puts "RESTORED_DMA [mrd -force -value 0x40020000 12]"
puts "RESTORED_DST [mrd -force -value 0x12bb00 12]"
disconnect
exit
