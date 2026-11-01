set root E:/zynqlinkPRO
set out $root/build/fclk-resume-20261101/debug-audit-v2
file mkdir $out
proc reports {out mode} {
    create_clock -name clk_fpga_0 -period 6.666 [get_ports clk]
    create_clock -name pad_swclk -period 16.666666 [get_ports swclk]
    set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks pad_swclk]
    report_utilization -file $out/utilization-$mode.rpt
    report_timing_summary -report_unconstrained -file $out/timing-$mode.rpt
    report_timing -max_paths 30 -file $out/setup-$mode.rpt
    set probes [get_cells -quiet -hier -filter {NAME =~ *clock_pad_rises_reg* || NAME =~ *transfer_trace_reg* || NAME =~ *diag_meta_reg* || NAME =~ *diag_front_reg* || NAME =~ *diag_latched_reg* || NAME =~ *diag_tx_reg* || NAME =~ *diag_sense_reg* || NAME =~ *diag_rx_reg* || NAME =~ *diag_extra_reg* || NAME =~ *diag_alternate_reg* || NAME =~ *diag_samples_reg*}]
    set fd [open $out/observations-$mode.txt w]
    puts $fd "MODE=$mode COUNT=[llength $probes]"
    foreach probe $probes {puts $fd $probe}
    close $fd
    if {$mode==0 && [llength $probes]} {error "Release retains optional probes"}
    if {$mode==1 && ![llength $probes]} {error "Debug probes absent"}
}
open_checkpoint $out/release-input.dcp
reports $out 0
close_project
create_project -in_memory -part xc7z020clg400-2
set_param general.maxThreads 4
set_property XPM_LIBRARIES {XPM_CDC XPM_FIFO XPM_MEMORY} [current_project]
read_verilog [list $root/fpga/rtl/dap_transfer_block_engine.v $root/fpga/rtl/jtag_core.v $root/fpga/rtl/jtag_shift.v $root/fpga/rtl/probe_rtt_engine.v $root/fpga/rtl/probe_sample_engine.v $root/fpga/rtl/probe_stream_engine.v $root/fpga/rtl/swd_batch_engine.v $root/fpga/rtl/swd_core.v $root/fpga/rtl/swd_controller.v $out/debug-wrapper.v]
synth_design -top system_swd_controller_0_0 -part xc7z020clg400-2 -mode out_of_context
reports $out 1
write_checkpoint -force $out/debug-synth.dcp
puts DEBUG_PROFILE_AUDIT_COMPLETE
