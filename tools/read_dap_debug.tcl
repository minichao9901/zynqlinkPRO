connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "dbg=[mrd 0x00100000 8]"
disconnect
