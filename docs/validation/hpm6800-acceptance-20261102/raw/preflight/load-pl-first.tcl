connect -url tcp:127.0.0.1:3121
after 1000
puts [targets]
puts [jtag targets]
targets -set -filter {name =~ "xc7z020"}
fpga -f {E:/zynqlinkPRO/prebuilt/golden/probe.bit}
after 500
puts [targets]
disconnect
exit
