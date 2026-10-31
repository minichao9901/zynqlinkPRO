connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
rst -system
set bp [bpadd -addr 0 -type hw -mode 2]
puts "WATCH_ID $bp"
for {set i 0} {$i < 4} {incr i} {
 set rc [catch {con -block -timeout 5} why]
 puts "WATCH_ITER $i RC $rc WHY $why"
 puts [rrd pc]
 puts [rrd r0]
 puts [rrd r1]
 puts [rrd r2]
 puts [rrd r3]
 puts [mrd -force 0 4]
 if {$rc} {break}
}
bpremove $bp
puts WATCH_REMOVED
catch {con}
puts [targets]

disconnect
exit
