connect -url tcp:127.0.0.1:3121
for {set n 0} {$n < 20} {incr n} {after 100}
puts [targets]
targets -set -filter {name =~ "APU"}
puts "AP0_OCM [mrd -address-space AP0 -force -value 0x0]"
disconnect
exit
