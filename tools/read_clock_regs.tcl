connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM*#0"}
puts [mrd 0xF8000100 4]
puts [mrd 0xF8000170 1]
disconnect
exit
