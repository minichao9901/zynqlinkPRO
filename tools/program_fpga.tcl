connect -url tcp:127.0.0.1:3121
set bit [file normalize [lindex $argv 0]]
puts "bit=$bit"
puts [targets]
targets -set -filter {name =~ "xc7z020"}
puts "programming"
fpga -f $bit
puts "programmed rc=$?"
after 500
targets -set -filter {name =~ "APU"}
puts "devcfg_status=[mrd 0xF800702C 1]"
disconnect
exit
