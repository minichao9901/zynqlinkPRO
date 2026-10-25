set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build fpga_dma_global]
open_project [file join $out zynqlink_dma.xpr]
set_param general.maxThreads 8
source [file join $root fpga configure_runs.tcl]
reset_run impl_1
set_property INCREMENTAL_CHECKPOINT {} [get_runs impl_1]
set_property strategy Performance_Explore [get_runs impl_1]
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "Implementation failed"}
source [file join $root fpga verify_routed.tcl]
