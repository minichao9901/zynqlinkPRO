connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "ARM*#0"}
mwr 0x3F000000 0
disconnect
exit
