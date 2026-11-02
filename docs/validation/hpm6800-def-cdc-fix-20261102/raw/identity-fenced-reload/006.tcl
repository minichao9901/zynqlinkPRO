connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
targets -set -filter {name =~ "APU"}
proc physrd {args} {return [mrd -address-space AP0 {*}$args]}
proc physwr {args} {return [mwr -address-space AP0 -bypass-cache-sync {*}$args]}
physrd -force -bin -file {E:/zynqlinkPRO/build/hpm6800-def-cdc-fix-20261102/identity-fenced-reload/live_code_0.bin} 0 19105
puts CODE_READ
disconnect
exit
