set root [file normalize [file join [file dirname [info script]] ../..]]
set out [file join $root build swd_rx_ooc]
file mkdir $out
set main_source [exec git -C $root show d42b60180e82fccb428c51613a0316776c2bc4fc:fpga/rtl/swd_core.v]
set main_file [open [file join $out main_swd_core.v] w]
puts $main_file $main_source
close $main_file
foreach label {main candidate} {
 create_project -in_memory -part xc7z020clg400-2
 if {$label eq "main"} {read_verilog [file join $out main_swd_core.v]} else {read_verilog [file join $root fpga rtl swd_core.v]}
 synth_design -top swd_core -part xc7z020clg400-2 -mode out_of_context
 create_clock -name fclk -period 10.000 [get_ports clk]
 set_false_path -from [get_ports rst_n]
 opt_design
 place_design
 route_design
 report_utilization -file [file join $out ${label}_util.rpt]
 report_timing_summary -file [file join $out ${label}_timing.rpt]
 report_timing -max_paths 5 -file [file join $out ${label}_paths.rpt]
 write_checkpoint -force [file join $out ${label}_routed.dcp]
 close_project
}
exit
