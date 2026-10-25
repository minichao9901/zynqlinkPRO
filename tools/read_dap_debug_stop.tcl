connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
stop
puts "dbg=[mrd 0x00100000 8]"
disconnect
