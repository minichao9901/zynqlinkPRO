connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "DAP*"}
rst -system
after 1000
configparams force-mem-access 1
puts [targets]
set argv [list prebuilt/hpm6800-usb-fixed-133-20261102/application.elf prebuilt/hpm6800-usb-fixed-133-20261102/probe.bit prebuilt/hpm6800-usb-fixed-133-20261102/ps7_init.tcl]
source tools/download_dap_fpga.tcl
