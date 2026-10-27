if {[catch {connect -url tcp:127.0.0.1:3121} err]} {
    connect
}
targets -set -filter {name =~ "APU"}
stop
puts [format "PC=0x%08x" [rrd pc]]
puts [format "FPGA0_CLK_CTRL=0x%08x" [mrd -force -value 0xF8000170]]
puts [format "JTAG_ROUTE=0x%08x" [mrd -force -value 0x40010080]]
puts [format "JTAG_HALF_Q=0x%08x" [mrd -force -value 0x400100cc]]
puts [format "SWD_FEATURES=0x%08x" [mrd -force -value 0x4001004c]]
con
