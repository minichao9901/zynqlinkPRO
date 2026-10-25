connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM*#0"}
stop
puts "qhd0/1"
puts [mrd -force 0x00201000 32]
puts "core and req data"
puts [mrd -force 0x00202E00 28]
puts "qtd ep0 in"
puts [mrd -force 0x00201700 8]
puts "config/counters"
puts [mrd -force 0x00203040 4]
puts [mrd -force 0x00200400 1]
puts [mrd -force 0xE00021C0 1]
con
disconnect
exit
