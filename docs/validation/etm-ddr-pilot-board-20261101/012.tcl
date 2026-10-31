connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000170 0x00300600
mwr -force 0xf8000004 0x767b
puts FCLK100_SELECTED
disconnect
exit
