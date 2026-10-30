# Reuse the fully linked generic 7-series synthesis netlist, then place/route
# on the actual 7010 resource grid. No 7020 placement or timing is reused.
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build fpga_7010]
file mkdir $out
source [file join $root fpga run_threads.tcl]
if {[lsearch -exact $argv --reuse-netlist] < 0} {
open_project [file join $root build fpga_dma_global zynqlink_dma.xpr]
open_run synth_1
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1 && REF_NAME != PS7}]]} {
    error "Synthesis design contains unresolved black boxes"
}
write_edif -force [file join $out system_wrapper.edf]
write_xdc -force [file join $out system.xdc]
close_project
}
create_project -in_memory -part xc7z010clg400-2
read_edif [file join $out system_wrapper.edf]
link_design -top system_wrapper -part xc7z010clg400-2
read_xdc [file join $out system.xdc]
create_clock -name clk_fpga_0 -period 8.333 [get_pins {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]
report_utilization -file [file join $out utilization_linked.rpt]
# A per-bit indexed receive write creates up to 256 unrelated clock enables.
# Keep the identical FF behavior but express those enables in the D inputs so
# the placer can pack the receive bank with the shared reset/clock control set.
set rx_regs [get_cells -hier -filter {REF_NAME =~ FD* && NAME =~ *u_shift/rx_data_reg*}]
if {![llength $rx_regs]} {error "JTAG RX registers missing before control-set optimization"}
set_property CONTROL_SET_REMAP ENABLE $rx_regs
puts "JTAG_RX_ENABLE_REMAP=[llength $rx_regs]"
opt_design
opt_design -control_set_opt
report_utilization -file [file join $out utilization_optimized.rpt]
report_control_sets -file [file join $out control_sets_optimized.rpt]
place_design -directive Explore
phys_opt_design -directive AggressiveExplore
route_design -directive Explore
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out utilization_hier.rpt]
report_control_sets -file [file join $out control_sets.rpt]
report_timing_summary -report_unconstrained -file [file join $out timing_120mhz.rpt]
report_timing -delay_type max -max_paths 20 -file [file join $out setup_paths.rpt]
report_timing -delay_type min -max_paths 20 -file [file join $out hold_paths.rpt]
write_checkpoint -force [file join $out system_routed.dcp]
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "ZYNQ7010_120MHZ SETUP=$setup HOLD=$hold"
if {$setup < 0 || $hold < 0} {error "7010 timing does not meet 120 MHz"}
write_bitstream -force [file join $out system_wrapper.bit]
puts "ZYNQ7010_BIT_READY $out/system_wrapper.bit (NOT BOARD VALIDATED)"
