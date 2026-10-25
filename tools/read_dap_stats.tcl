connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "STATS=[mrd 0x00121e24 8]"
puts "DBG=[mrd 0x00100000 2]"
disconnect
exit
