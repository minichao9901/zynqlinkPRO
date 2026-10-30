set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build fpga_dma_global]
open_checkpoint [file join $out zynqlink_dma.runs impl_1 system_wrapper_routed.dcp]
# A forward reference inside a generate block can become an undriven local
# net in Vivado 2018.3, silently tying every GPIO IOBUF's T pin high. Reject
# that netlist even if internal STA passes; the two-wire loopback caught it.
foreach pad [get_cells -hier -filter {REF_NAME == IOBUF && NAME =~ *g_aux*}] {
    set tpin [get_pins -of_objects $pad -filter {REF_PIN_NAME == T}]
    set tnet [get_nets -of_objects $tpin]
    set driver [get_cells -of_objects [get_pins -of_objects $tnet -filter {DIRECTION == OUT}]]
    if {[llength [filter $driver {REF_NAME == VCC || REF_NAME == GND}]]} {
        error "GPIO pad output-enable is constant: $pad ($tnet)"
    }
}
set packet_bram [get_cells -hier -filter {REF_NAME =~ RAMB* && NAME =~ *u_packet_bram*}]
if {[llength $packet_bram] < 4} {error "PL packet banks did not implement in block RAM"}
puts "PACKET_BRAM_VERIFIED count=[llength $packet_bram]"
set tdo_ddr [get_cells -hier -filter {REF_NAME == IDDR && NAME =~ *u_tdo_iddr}]
if {[llength $tdo_ddr] != 1} {error "JTAG TDO IDDR missing from implemented design"}
foreach phase {Q1 Q2} {
    set net [get_nets -of_objects [get_pins $tdo_ddr/$phase]]
    if {![llength [get_pins -of_objects $net -filter {DIRECTION == IN}]]} {
        error "JTAG TDO IDDR $phase was optimized out or bypassed"
    }
}
puts "JTAG_TDO_IDDR_VERIFIED LOC=[get_property LOC $tdo_ddr] phases=Q1,Q2"
set trace_ddr [get_cells -hier -filter {REF_NAME == IDDR && NAME =~ *orbtrace_0*}]
if {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) in {2 3}} {
    if {[llength $trace_ddr] != 0} {error "Oversample mode must bypass normal TRACE IDDRs"}
    puts "ORBTRACE_IDDR_BYPASS_VERIFIED mode=$::env(ZYNQLINK_RAW_TRACE)"
} elseif {[llength $trace_ddr] != 4} {error "Parallel TRACE must retain four input IDDRs"}
set trace_bufio [get_cells -hier -filter {REF_NAME == BUFIO && NAME =~ *orbtrace_0*}]
set trace_bufr [get_cells -hier -filter {REF_NAME == BUFR && NAME =~ *orbtrace_0*}]
if {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) in {2 3}} {
    puts "ORBTRACE_CLOCK_BYPASS_VERIFIED mode=$::env(ZYNQLINK_RAW_TRACE) BUFIO=[llength $trace_bufio] BUFR=[llength $trace_bufr]"
} elseif {[llength $trace_bufio] != 1 || [llength $trace_bufr] != 1} {
    error "Parallel TRACE dedicated I/O/fabric clock buffers missing"
}
if {[llength [get_cells -hier -filter {NAME =~ *orbtrace_0* && (REF_NAME == LDCE || REF_NAME == LDPE || REF_NAME == LDCPE)}]]} {
    error "Parallel TRACE contains unintended latches"
}
puts "ORBTRACE_IO_VERIFIED IDDR=[llength $trace_ddr] BUFIO=[llength $trace_bufio] BUFR=[llength $trace_bufr] latches=0"
set trace_idelay [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *orbtrace_0*}]
set trace_idelayctrl [get_cells -hier -filter {REF_NAME == IDELAYCTRL && NAME =~ *orbtrace_0*}]
if {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) in {2 3}} {
    puts "ORBTRACE_DELAY_BYPASS_VERIFIED mode=$::env(ZYNQLINK_RAW_TRACE) IDELAYE2=[llength $trace_idelay] IDELAYCTRL=[llength $trace_idelayctrl]"
} elseif {[llength $trace_idelay] != 4 || [llength $trace_idelayctrl] != 1} {
    error "Parallel TRACE input delay/calibration primitives missing"
} else {
    puts "ORBTRACE_DELAY_VERIFIED IDELAYE2=4 IDELAYCTRL=1 REFCLK=200MHz"
}
if {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) in {2 3}} {
    set os_meta [get_cells -quiet -hier -filter {NAME =~ *raw_oversample*pad_meta_reg*}]
    set os_sync [get_cells -quiet -hier -filter {NAME =~ *raw_oversample*pad_sync_reg*}]
    if {[llength $os_meta] != 5 || [llength $os_sync] != 5} {
        error "Raw oversampling synchronizers missing: meta=[llength $os_meta] sync=[llength $os_sync]"
    }
    puts "ORBTRACE_OVERSAMPLE_VERIFIED META=[llength $os_meta] SYNC=[llength $os_sync]"
}
# Evaluate realizable PLL divisors on this routed netlist, without rebuilding
# it for each frequency. Keep the highest rate that meets BOTH setup and hold.
set verified_fclk 0
set fd [open [file join $out frequency_timing.csv] w]
puts $fd "FCLK_Hz,setup_slack_ns,hold_slack_ns"
foreach rate {180000000 163636364 150000000 138461539 128571429 120000000 100000000} {
    create_clock -name clk_fpga_0 -period [expr {floor(1e12/$rate)/1000.0}] [get_pins {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]
    set setup [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]
    set h [get_property SLACK [get_timing_paths -max_paths 1 -delay_type min]]
    puts $fd "$rate,$setup,$h"
    puts "FREQUENCY_CHECK FCLK=$rate SETUP=$setup HOLD=$h"
    if {$setup >= 0 && $h >= 0} {set verified_fclk $rate; break}
}
close $fd
if {!$verified_fclk} {
    report_clocks -file [file join $out clocks_failed.rpt]
    report_utilization -file [file join $out utilization_failed.rpt]
    report_timing_summary -report_unconstrained -file [file join $out timing_failed.rpt]
    error "Routed timing failed at every tested frequency"
}
report_clocks -file [file join $out clocks_verified.rpt]
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out utilization_hier.rpt]
report_timing_summary -report_unconstrained -file [file join $out timing_verified.rpt]
set worst [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]
set hold [get_property SLACK [get_timing_paths -max_paths 1 -delay_type min]]
puts "VERIFIED_SETUP_SLACK=$worst VERIFIED_HOLD_SLACK=$hold"
if {$worst < 0 || $hold < 0} {error "Routed timing failed with all FCLK input sampling paths constrained"}
write_checkpoint -force [file join $out system_wrapper_verified.dcp]
set run_bit [file join $out zynqlink_dma.runs impl_1 system_wrapper.bit]
set run_dcp [file join $out zynqlink_dma.runs impl_1 system_wrapper_routed.dcp]
if {[file exists $run_bit] && [file mtime $run_bit] >= [file mtime $run_dcp]} {
    # STA does not change configuration bits. Avoid a duplicate bitgen when
    # an existing project run already generated this routed design's bit.
    file copy -force $run_bit [file join $out system_wrapper_verified.bit]
} else {
    write_bitstream -force [file join $out system_wrapper_verified.bit]
}
file copy -force [file join $out system_wrapper_verified.bit] [file join $out system_wrapper.bit]
# Publish timing metadata only after bitgen and its DRC succeed. A failed new
# route must not relabel the old bitstream with a new verified clock limit.
set fd [open [file join $out verified_clock.json] w]
puts $fd "{\"FCLK_max_Hz\":$verified_fclk,\"SWCLK_max_Hz\":[expr {$verified_fclk/2}],\"setup_slack_ns\":$worst,\"hold_slack_ns\":$hold}"
close $fd
file mkdir [file join $root build checkpoints]
file copy -force [file join $out system_wrapper_verified.dcp] [file join $root build checkpoints dma_routed_reference.dcp]
puts "VERIFIED_BITSTREAM_READY"
