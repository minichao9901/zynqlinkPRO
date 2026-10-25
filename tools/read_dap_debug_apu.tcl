connect
targets -set -filter {name =~ "APU"}
puts "dbg=[mrd 0x00100000 8]"
disconnect
