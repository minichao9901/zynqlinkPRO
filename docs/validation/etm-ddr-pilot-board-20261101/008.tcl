connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
puts "HP0 [mrd -force -value 0xf8008000 10]"
puts "HP1 [mrd -force -value 0xf8009000 10]"
puts "ISOLATION [mrd -force -value 0xf8000900] [mrd -force -value 0xf8000240]"
mwr -force 0x4004000c 0x10000000
mwr -force 0x40040010 1048576
mwr -force 0x40040014 0x13dba917
mwr -force 0x40040004 1
after 100
puts "SECOND_PATTERN [mrd -force -value 0x40040000 16]"
disconnect
exit
