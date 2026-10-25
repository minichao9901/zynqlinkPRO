connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "PSTAT=[mrd 0x40010048 1]"
puts "PLEN=[mrd 0x40010044 1]"
puts "BSTAT=[mrd 0x40010034 1]"
puts "CTRL=[mrd 0x40010000 1]"
disconnect
exit
