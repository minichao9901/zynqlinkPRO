set root [file normalize [file join [file dirname [info script]] ../..]]
source [file join $root fpga repair_probe_io.tcl]
set repaired_output $out
close_design
set ::zynqlink_verify_out $repaired_output
set ::zynqlink_verify_checkpoint [file join $repaired_output system_wrapper_routed.dcp]
set ::zynqlink_verify_bit [file join $repaired_output system_wrapper.bit]
source [file join $root fpga verify_routed.tcl]
