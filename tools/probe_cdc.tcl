connect -url tcp:127.0.0.1:3121
after 1000
targets -set -filter {name =~ "ARM*#0"}
stop
puts "CPU:"
puts [rrd pc]
puts [rrd cpsr]
puts "USB:"
puts [mrd -force 0xE0002140 2]
puts [mrd -force 0xE0002184]
puts "Noncacheable telemetry:"
puts [mrd -force 0x00200400 40]
con
disconnect
exit

