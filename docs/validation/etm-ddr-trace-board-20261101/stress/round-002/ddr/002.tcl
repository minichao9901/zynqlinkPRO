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
physwr -force 0x40040040 399999996
physwr -force 0x4004007c 3076354945
physwr -force 0x40040080 4144276181
set arm_before_ms [clock milliseconds]
physwr -force 0x40040004 1
set terminal 0
set marked 0
for {set n 0} {$n<10000} {incr n} {
  set status [physrd -force -value 0x40040008]
  set id [physrd -force -value 0x40040028]
  if {!$marked && ($status&32) && $id==5} {
    set f [open {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-trace-stress-20261101/round-002/ddr/armed.json.tmp} w]
    puts $f [format {{"armBeforeMs":%s,"activeObservedMs":%s}} $arm_before_ms [clock milliseconds]]
    close $f;file rename {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-trace-stress-20261101/round-002/ddr/armed.json.tmp} {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-trace-stress-20261101/round-002/ddr/armed.json};set marked 1
  }
  if {[file exists {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-trace-stress-20261101/round-002/ddr/cancel}] && ($status&1)} {catch {physwr -force 0x40040004 2}}
  if {$id==5 && !($status&1) && ($status&2)} {set terminal 1;break}
  after 1
}
puts "TRACE_DDR_REGS [physrd -force -value 0x40040000 34]"
if {!$terminal} {catch {physwr -force 0x40040004 2};error "capture timed out; stop requested"}

disconnect
exit
