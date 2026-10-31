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
physwr -force 0x4004003c 2
physwr -force 0x4004000c 0x10000000
physwr -force 0x40040010 67108864
physwr -force 0x40040040 199999998
physwr -force 0x4004007c 422890822
physwr -force 0x40040080 1111177165
physwr -force 0x40040004 1
set terminal 0
set marked 0
for {set n 0} {$n<10000} {incr n} {
  set status [physrd -force -value 0x40040008]
  set id [physrd -force -value 0x40040028]
  if {!$marked && ($status&32) && $id==3} {
    set f [open {build/etm-ddr-trace-first-1s-20261101/ddr/armed.json} w];puts $f {"armed"};close $f;set marked 1
  }
  if {[file exists {build/etm-ddr-trace-first-1s-20261101/ddr/cancel}] && ($status&1)} {catch {physwr -force 0x40040004 2}}
  if {$id==3 && !($status&1) && ($status&2)} {set terminal 1;break}
  after 1
}
puts "TRACE_DDR_REGS [physrd -force -value 0x40040000 34]"
if {!$terminal} {catch {physwr -force 0x40040004 2};error "capture timed out; stop requested"}

disconnect
exit
