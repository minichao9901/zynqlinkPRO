connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM*#0"}
stop
puts "CPU view"
puts [mrd -force 0x201040 4]
targets -set -filter {name == "APU"}
puts "APU view"
puts [mrd -force 0x201040 4]
puts [mrd -force 0x201700 4]
targets -set -filter {name =~ "ARM*#0"}
con
disconnect
exit
