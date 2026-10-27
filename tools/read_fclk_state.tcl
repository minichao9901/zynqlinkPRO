# Read back the clock programming the DAP firmware just applied.
# Usage: xsct tools/read_fclk_state.tcl
if {[catch {connect -url tcp:127.0.0.1:3121} err]} {
    connect
}
targets -set -filter {name =~ "APU"}
stop
puts [format "IO_PLL_CTRL     0xF8000108 = 0x%08X" [mrd -force -value 0xF8000108]]
puts [format "FPGA0_CLK_CTRL  0xF8000170 = 0x%08X" [mrd -force -value 0xF8000170]]
puts [format "FPGA1_CLK_CTRL  0xF8000180 = 0x%08X" [mrd -force -value 0xF8000180]]
puts [format "CLK_621_TRUE    0xF80001C4 = 0x%08X" [mrd -force -value 0xF80001C4]]
set reg [mrd -force -value 0xF8000170]
set src [expr {($reg >> 4) & 0x3}]
set d0  [expr {($reg >> 8) & 0x3F}]
set d1  [expr {($reg >> 20) & 0x3F}]
set pll [mrd -force -value 0xF8000108]
set fbdiv [expr {($pll >> 12) & 0x7F}]
set io_pll [expr {33333333 * $fbdiv}]
puts [format "IO_PLL=%d Hz  src=%d  DIV0=%d  DIV1=%d" $io_pll $src $d0 $d1]
if {$d0 != 0 && $d1 != 0} {
    puts [format "FCLK0 = %d Hz  -> TCK = %d Hz" [expr {$io_pll/$d0/$d1}] [expr {$io_pll/$d0/$d1/2}]]
}
con
