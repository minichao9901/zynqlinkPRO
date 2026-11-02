# Bound the short SWCLK launch path independently of register-to-register STA.
# The merged RAW4 placement increased this path from 7.417ns to 8.400ns at
# the slow corner, and SWD25 continuous RTT failed while the old PL passed.
# Keep a 7ns internal clock-to-pad budget; board regression remains required.
set swclk_launch [get_cells -quiet -hier -filter {NAME =~ *short_core_clock_reg}]
if {[llength $swclk_launch] != 1} {error "Short SWCLK launch register missing/ambiguous"}
set swclk_pad [get_ports swclk_0]
set_max_delay 7.000 -datapath_only -from $swclk_launch -to $swclk_pad
puts "SWCLK_LAUNCH_BUDGET=7.000ns SOURCE=$swclk_launch"
# Optional internal work point for placement/route, not the target TRACECLK.
# The default XDC closes 133.333333MHz, independently of the lower FCLK a
# transaction may select at runtime. Explicit experiments may override it.
if {[info exists ::env(ZYNQLINK_IMPLEMENT_FCLK_HZ)]} {
    set implementation_hz $::env(ZYNQLINK_IMPLEMENT_FCLK_HZ)
    if {![string is integer -strict $implementation_hz] || $implementation_hz < 10000000 || $implementation_hz > 180000000} {
        error "ZYNQLINK_IMPLEMENT_FCLK_HZ must be 10000000..180000000"
    }
    create_clock -name clk_fpga_0 -period [expr {1e9/$implementation_hz}] [get_pins {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]
    puts "IMPLEMENTATION_FCLK_HZ=$implementation_hz"
}
