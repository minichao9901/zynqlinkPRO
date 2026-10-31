# Constrain and repair I/O launch timing on a known routed checkpoint.
# RTL is unchanged. Record the input DCP identity alongside the new bitstream.
if {[llength $argv] != 2} {error "Expected input routed DCP and new output directory"}
set root [file normalize [file join [file dirname [info script]] ..]]
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
if {[file exists $out]} {error "Use a fresh output directory"}
file mkdir $out
source [file join $root fpga run_threads.tcl]
open_checkpoint $checkpoint
source [file join $root fpga probe_io_timing.tcl]
phys_opt_design -directive AggressiveExplore
route_design -directive Explore
report_timing -from $swclk_launch -to $swclk_pad -max_paths 2 -file $out/swclk_launch.rpt
report_timing_summary -report_unconstrained -file $out/timing.rpt
report_utilization -file $out/utilization.rpt
report_timing -delay_type max -max_paths 20 -file $out/setup.rpt
report_timing -delay_type min -max_paths 20 -file $out/hold.rpt
write_checkpoint -force $out/system_wrapper_routed.dcp
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
set launch [get_property SLACK [get_timing_paths -from $swclk_launch -to $swclk_pad -max_paths 1]]
puts "IO_REPAIR_SETUP=$setup HOLD=$hold SWCLK_SLACK=$launch"
if {$setup < 0 || $hold < 0 || $launch < 0} {error "I/O repair failed timing"}
write_bitstream -force $out/system_wrapper.bit
puts "IO_REPAIR_BIT_READY $out/system_wrapper.bit"
