connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM*#0"}
catch {stop}
puts [rrd pc]
puts [rrd r1]
puts [mrd -force 0x201040 8]
puts [mrd -force 0x201700 8]
puts [mrd -force 0xE00021B0 4]
bpremove -all
con
after 500
catch {stop}
puts "after prime"
puts [mrd -force 0x201040 8]
puts [mrd -force 0x201700 8]
con
disconnect
exit
