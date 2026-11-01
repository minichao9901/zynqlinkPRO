connect -url tcp:127.0.0.1:3121
after 1000
puts [targets]
targets -set -filter {name == "DAP"}
puts "RESET_DAP_BEGIN"
if {[catch {rst -system} why]} {puts "RESET_FAILED $why"} else {puts RESET_SENT}
after 1000
puts [targets]
disconnect
exit
