connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM*#0"}
stop
puts [mrd -force 0x00200000 4]
puts [mrd -force 0x00200200 4]
puts [mrd -force 0x00200800 8]
puts [mrd -force 0x00201000 16]
puts [mrd -force 0x00300000 8]
puts [mrd -force 0xE0002140 8]
puts [mrd -force 0xE00021A8 6]
puts [mrd -force 0x00110008 1]
mwr -force 0x00200400 0
puts "after clear"
puts [mrd -force 0x00200400 1]
con
disconnect
exit
