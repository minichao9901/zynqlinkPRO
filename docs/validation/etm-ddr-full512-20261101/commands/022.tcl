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
physrd -force -bin -file {E:/zynqlinkPRO_etm_calibration/build/etm-ddr-state-isolation-20261101/physical-full512/round-001/ddr-part-017.bin} 0x21000000 4194304
puts PHYSICAL_CHUNK_READ
disconnect
exit
