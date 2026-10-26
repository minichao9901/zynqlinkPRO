# Fast resource regression: sample storage must infer RAM, not 16K flip-flops.
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build probe_sample_synth]
file mkdir $out
read_verilog [file join $root fpga rtl probe_sample_engine.v]
synth_design -top probe_sample_engine -mode out_of_context -part xc7z020clg400-2
create_clock -period 10 [get_ports clk]
report_utilization -file [file join $out utilization.rpt]
report_timing_summary -file [file join $out timing.rpt]
set ram_cells [get_cells -hier -filter {REF_NAME =~ RAM*}]
if {![llength $ram_cells]} {error "Sampler FIFO did not infer RAM"}
set ff_cells [get_cells -hier -filter {REF_NAME =~ FD*}]
if {[llength $ff_cells] > 5000} {error "Sampler unexpectedly uses too many flip-flops"}
puts "PROBE_RAM_PASS RAM_CELLS=[llength $ram_cells] FF_CELLS=[llength $ff_cells]"
exit
