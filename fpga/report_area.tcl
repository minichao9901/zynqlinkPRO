# Read-only area investigation of a specific implemented checkpoint.
set root [file normalize [file join [file dirname [info script]] ..]]
set dcp [file join $root build fpga_dma_global zynqlink_dma.runs impl_1 system_wrapper_routed.dcp]
if {[llength $argv]} {set dcp [file normalize [lindex $argv 0]]}
set out [file join $root build orbtrace_area]
file mkdir $out
open_checkpoint $dcp
report_utilization -file [file join $out routed_utilization.rpt]
report_utilization -hierarchical -hierarchical_depth 8 -file [file join $out hierarchy.rpt]
report_control_sets -verbose -file [file join $out control_sets.rpt]
puts "AREA_REPORTS_READY $out"
