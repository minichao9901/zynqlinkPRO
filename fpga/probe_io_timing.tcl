# Bound the short SWCLK launch path independently of register-to-register STA.
# The merged RAW4 placement increased this path from 7.417ns to 8.400ns at
# the slow corner, and SWD25 continuous RTT failed while the old PL passed.
# Keep a 7ns internal clock-to-pad budget; board regression remains required.
set swclk_launch [get_cells -quiet -hier -filter {NAME =~ *short_core_clock_reg}]
if {[llength $swclk_launch] != 1} {error "Short SWCLK launch register missing/ambiguous"}
set swclk_pad [get_ports swclk_0]
set_max_delay 7.000 -datapath_only -from $swclk_launch -to $swclk_pad
puts "SWCLK_LAUNCH_BUDGET=7.000ns SOURCE=$swclk_launch"
