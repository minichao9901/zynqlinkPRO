# Re-time an existing routed netlist at several FCLK rates. No synthesis,
# placement, routing, or bitstream generation is performed.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[llength $argv] > 0} {set checkpoint [lindex $argv 0]} else {
    set checkpoint [file join $root build fpga_dma_global zynqlink_dma.runs impl_1 system_wrapper_routed.dcp]
}
open_checkpoint $checkpoint
set out [file join $root results optimization clock_limits]
file mkdir $out
set fd [open [file join $out internal_timing.csv] w]
puts $fd "SWCLK_Hz,FCLK_Hz,setup_slack_ns,hold_slack_ns"
foreach swclk_hz {50000000 60000000 75000000 81818182 90000000} {
    set fclk_hz [expr {2.0*$swclk_hz}]
    create_clock -name clk_fpga_0 -period [expr {1e9/$fclk_hz}] [get_pins {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]
    set setup [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]
    set hold [get_property SLACK [get_timing_paths -max_paths 1 -delay_type min]]
    puts $fd "$swclk_hz,$fclk_hz,$setup,$hold"
    puts "CLOCK_LIMIT SWCLK=$swclk_hz SETUP=$setup HOLD=$hold"
    report_timing_summary -report_unconstrained -file [file join $out timing_${swclk_hz}.rpt]
}
close $fd

