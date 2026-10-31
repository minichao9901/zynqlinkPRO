connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
puts "SECOND_PILOT_DMA [mrd -force -value 0x40020000 12]"
puts "HP0 [mrd -force -value 0xf8008000 12]"
puts "HP1 [mrd -force -value 0xf8009000 12]"
puts "ISOLATION [mrd -force -value 0xf8000900] [mrd -force -value 0xf8000240]"
disconnect
exit
