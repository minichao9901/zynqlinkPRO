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

set before [physrd -force -value 0x40030050 6]
if {[lindex $before 0] != 1162626097} {error "ELD1 capability missing; no write"}
if {!([physrd -force -value 0x40030048] & 0x100)} {error "DDR CSR not advertised; no write"}
if {([physrd -force -value 0x40030004] & 1) || ([physrd -force -value 0x40040008] & 1)} {error "Capture active; no tap write"}
if {([lindex $before 2] & 2) || !([physrd -force -value 0x40030008] & 8)} {error "Pending tap load or IDELAYCTRL not ready; no write"}
physwr -force 0x40030054 0xb7fc4100
set done 0
for {set attempt 0} {$attempt < 100} {incr attempt} {
 set current [physrd -force -value 0x40030050 6]
 if {[lindex $current 4] != [lindex $before 4]} {error "Hardware rejected tap command; no replay"}
 if {[lindex $current 3] == (([lindex $before 3]+1)&0xffffffff) && !([lindex $current 2]&2)} {set done 1;break}
 after 1
}
if {!$done} {error "Tap acknowledge timeout; no replay"}
if {[lindex $current 1] != 66863360 || ([lindex $current 2]&0x1c)!=0x0c || [lindex $current 5] != [lindex $before 5]} {error "Tap readback/load failed"}
puts "ELD_BEFORE $before"
puts "ELD_AFTER $current"

disconnect
exit
