connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "taken=[mrd 0x00122054 1]"
puts "fallback=[mrd 0x00122048 1]"
puts "status=[mrd 0x0012204c 1]"
puts "req=[mrd 0x00122044 1]"
puts "count=[mrd 0x00122050 1]"
puts "rsp0=[mrd 0x00122078 1]"
disconnect
exit
