connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "stats=[mrd 0x00100000 10]"
disconnect
