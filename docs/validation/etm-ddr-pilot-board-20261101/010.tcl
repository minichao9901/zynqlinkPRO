connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
mwr -force 0x40040014 0x27abcdef
mwr -force 0x40040004 1
after 100
puts "PATTERN_120 [mrd -force -value 0x40040000 16]"
disconnect
exit
