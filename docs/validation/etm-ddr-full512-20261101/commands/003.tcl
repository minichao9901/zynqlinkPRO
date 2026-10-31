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
physwr -force 0x4004000c 0x10000000
physwr -force 0x40040010 536870912
physwr -force 0x40040014 333162775
physwr -force 0x40040004 1
set terminal 0
for {set n 0} {$n<10000} {incr n} {
  set id [physrd -force -value 0x40040028]
  set status [physrd -force -value 0x40040008]
  if {$id==1 && !($status&1) && ($status&2)} {set terminal 1;break}
  after 1
}
puts "DDR_STATUS [physrd -force -value 0x40040000 16]"
if {!$terminal} {
  catch {physwr -force 0x40040004 2}
  error "Writer timeout; abort requested, pending AXI retirement not proven"
}

disconnect
exit
