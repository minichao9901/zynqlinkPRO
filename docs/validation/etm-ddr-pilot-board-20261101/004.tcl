connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
mwr -force 0x4004000c 0x10000000
mwr -force 0x40040010 1048576
mwr -force 0x40040014 0x13dba917
mwr -force 0x40040004 1
set terminal 0
for {set n 0} {$n<1000} {incr n} {
 set status [mrd -force -value 0x40040008]
 if {!($status&1)} {set terminal 1;break}
 after 1
}
puts "PILOT_STATUS [mrd -force -value 0x40040000 16]"
if {!$terminal} {error "Pilot not terminal"}

disconnect
exit
