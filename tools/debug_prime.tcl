connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM*#0"}
stop
set bp [bpadd -addr 0x00100FD4 -type hw]
mwr -force 0xE0002140 0
after 500
mwr -force 0xE0002140 1
con
after 1500
puts [targets]
stop
puts [rrd pc]
puts [rrd r1]
puts [mrd -force 0x201040 8]
puts [mrd -force 0x201700 8]
bpremove $bp
con
disconnect
exit
