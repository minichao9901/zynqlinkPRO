set root E:/zynqlinkPRO
set out $root/build/fclk-resume-20261101/final-rerate-138-analysis
file mkdir $out
open_checkpoint $root/build/fclk-resume-20261101/final-routed-150.dcp
create_clock -name clk_fpga_0 -period 7.222 [get_pins {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]
report_timing_summary -report_unconstrained -file $out/timing.rpt
report_timing -delay_type max -max_paths 30 -file $out/setup.rpt
report_timing -delay_type min -max_paths 30 -file $out/hold.rpt
report_timing -delay_type max -to [all_registers -async_pins] -max_paths 10 -file $out/recovery.rpt
report_timing -delay_type min -to [all_registers -async_pins] -max_paths 10 -file $out/removal.rpt
check_timing -verbose -file $out/check_timing.rpt
report_clocks -file $out/clocks.rpt
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
set summary [report_timing_summary -return_string]
set passed [expr {[string match {*All user specified timing constraints are met.*} $summary]}]
set fd [open $out/result.json w]
puts $fd "{\"analysisOnly\":true,\"newImplementation\":false,\"bitstreamGenerated\":false,\"hardwareAccess\":false,\"FCLK_Hz\":138461539,\"setupNs\":$setup,\"holdNs\":$hold,\"allSpecifiedChecksPassed\":$passed}"
close $fd
puts "RERATE_ONLY setup=$setup hold=$hold allSpecifiedChecks=$passed"
