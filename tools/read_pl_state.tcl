connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "PC=[rrd pc]"
puts "GPIO40000000=[mrd 0x40000000 1]"
puts "SWD40010000=[mrd 0x40010000 1]"
puts "SWD40010004=[mrd 0x40010004 1]"
puts "DDR100000=[mrd 0x00100000 1]"
disconnect
