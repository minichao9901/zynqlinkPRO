set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build fpga_dma_global]
if {[info exists ::zynqlink_verify_out]} {set out [file normalize $::zynqlink_verify_out]}
set routed_checkpoint [file join $out zynqlink_dma.runs impl_1 system_wrapper_routed.dcp]
if {[info exists ::zynqlink_verify_checkpoint]} {set routed_checkpoint [file normalize $::zynqlink_verify_checkpoint]}
open_checkpoint $routed_checkpoint
source [file join $root fpga rtl_debug_profile.tcl]
set rtl_debug [zynqlink_rtl_debug_mode $argv]
set requested_fclk 133333333
if {[info exists ::env(ZYNQLINK_IMPLEMENT_FCLK_HZ)]} {set requested_fclk $::env(ZYNQLINK_IMPLEMENT_FCLK_HZ)}
if {![string is integer -strict $requested_fclk] || $requested_fclk<10000000 || $requested_fclk>200000000} {
    error "Verification FCLK must be 10000000..200000000"
}
set observation_cells [get_cells -quiet -hier -filter {NAME =~ *swd_controller_0* && (NAME =~ *clock_pad_rises_reg* || NAME =~ *transfer_trace_reg* || NAME =~ *diag_meta_reg* || NAME =~ *diag_front_reg*)}]
if {!$rtl_debug && [llength $observation_cells]} {error "Release retains optional observation registers"}
if {$rtl_debug && ![llength $observation_cells]} {error "Debug instrumentation was not implemented"}
puts "RTL_OBSERVATION_IMPLEMENTED=[llength $observation_cells] RTL_DEBUG=$rtl_debug"
set swclk_launch [get_cells -quiet -hier -filter {NAME =~ *short_core_clock_reg}]
if {[llength $swclk_launch] != 1} {error "SWCLK launch register missing"}
set swclk_path [get_timing_paths -from $swclk_launch -to [get_ports swclk_0] -max_paths 1]
if {![llength $swclk_path] || [get_property REQUIREMENT $swclk_path] > 7.001 || [get_property SLACK $swclk_path] < 0} {
    error "Short SWCLK clock-to-pad path is missing its passing <=7ns budget"
}
report_timing -from $swclk_launch -to [get_ports swclk_0] -max_paths 2 -file [file join $out swclk_launch.rpt]
puts "SWCLK_LAUNCH_VERIFIED slack=[get_property SLACK $swclk_path]"
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
if {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) in {2 3 4}} {
    if {[llength $trace_ddr] != 0} {error "Oversample mode must bypass normal TRACE IDDRs"}
    puts "ORBTRACE_IDDR_BYPASS_VERIFIED mode=$::env(ZYNQLINK_RAW_TRACE)"
} elseif {[llength $trace_ddr] != 4} {error "Parallel TRACE must retain four input IDDRs"}
set trace_bufio [get_cells -hier -filter {REF_NAME == BUFIO && NAME =~ *orbtrace_0*}]
set trace_bufr [get_cells -hier -filter {REF_NAME == BUFR && NAME =~ *orbtrace_0*}]
if {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) in {2 3 4}} {
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
if {[info exists ::env(ZYNQLINK_ETM_LANE_DELAY)] && $::env(ZYNQLINK_ETM_LANE_DELAY)==1} {
    if {[llength $trace_idelay]!=5 || [llength $trace_idelayctrl]!=1} {error "Five active per-lane IDELAYE2 inputs and IDELAYCTRL are required"}
    set trace_sampling_sinks {}
    foreach cell $trace_idelay {
        if {[get_property IDELAY_TYPE $cell] ne "VAR_LOAD"} {error "Per-lane delay is not dynamically loadable: $cell"}
        # DATAOUT now crosses module ports directly. A local net segment has
        # no leaf load inside this hierarchy; follow it to the actual sampler.
        set endpoints [all_fanout -flat -endpoints_only -from [get_pins $cell/DATAOUT]]
        set users [filter $endpoints {NAME =~ *raw_oversample_filtered*pad_meta_reg*/D}]
        if {![llength $users]} {error "Input delay output is unused: $cell"}
        foreach sink $users {lappend trace_sampling_sinks $sink}
        puts "ORBTRACE_LANE_ENDPOINT $cell -> $users"
    }
    if {[llength [lsort -unique $trace_sampling_sinks]]!=5} {error "Five distinct physical sampler endpoints required"}
    puts "ORBTRACE_LANE_ENDPOINTS_VERIFIED count=5"
    puts "ORBTRACE_LANE_DELAY_VERIFIED count=5 VAR_LOAD=1 activeOutputs=5"
} elseif {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) in {2 3 4}} {
    puts "ORBTRACE_DELAY_BYPASS_VERIFIED mode=$::env(ZYNQLINK_RAW_TRACE) IDELAYE2=[llength $trace_idelay] IDELAYCTRL=[llength $trace_idelayctrl]"
} elseif {[llength $trace_idelay] != 4 || [llength $trace_idelayctrl] != 1} {
    error "Parallel TRACE input delay/calibration primitives missing"
} else {
    puts "ORBTRACE_DELAY_VERIFIED IDELAYE2=4 IDELAYCTRL=1 REFCLK=200MHz"
}
if {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) in {2 3 4}} {
    set os_meta [get_cells -quiet -hier -filter {NAME =~ *raw_oversample*pad_meta_reg*}]
    set os_sync [get_cells -quiet -hier -filter {NAME =~ *raw_oversample*pad_sync_reg*}]
    if {[llength $os_meta] != 5 || [llength $os_sync] != 5} {
        error "Raw oversampling synchronizers missing: meta=[llength $os_meta] sync=[llength $os_sync]"
    }
    puts "ORBTRACE_OVERSAMPLE_VERIFIED META=[llength $os_meta] SYNC=[llength $os_sync]"
}
# Evaluate realizable PLL divisors on this routed netlist, without rebuilding
# it for each frequency. Keep the highest rate that meets BOTH setup and hold.
# Preserve a direct report at the requested work point, even if a higher
# exploratory frequency passes first or the script later falls back to 100MHz.
create_clock -name clk_fpga_0 -period [expr {floor(1e12/$requested_fclk)/1000.0}] [get_pins {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]
report_timing_summary -report_unconstrained -file [file join $out timing_target.rpt]
report_timing -delay_type max -max_paths 60 -file [file join $out setup_target.rpt]
report_timing -delay_type min -max_paths 60 -file [file join $out hold_target.rpt]
report_timing -delay_type max -to [all_registers -async_pins] -max_paths 30 -file [file join $out recovery_target.rpt]
report_timing -delay_type min -to [all_registers -async_pins] -max_paths 30 -file [file join $out removal_target.rpt]
foreach sampler {u_swdio_iddr u_tdo_iddr} {
    foreach phase {Q1 Q2} {
        set sample_pin [get_pins -quiet -hier -filter "NAME =~ */$sampler/$phase"]
        if {[llength $sample_pin]} {
            report_timing -from $sample_pin -delay_type max -max_paths 12 -file [file join $out setup_${sampler}_${phase}.rpt]
            report_timing -from $sample_pin -delay_type min -max_paths 12 -file [file join $out hold_${sampler}_${phase}.rpt]
        }
    }
}
# One aggregate top-N can hide a second path family behind many byte-counter
# endpoints. Keep independent endpoint reports for each functional block.
foreach {family pattern} {ddr *etm_ddr_0* debug *swd_controller_0* cdma *cdma*} {
    set endpoints [get_cells -quiet -hier -filter "NAME =~ $pattern && IS_SEQUENTIAL == 1"]
    if {[llength $endpoints]} {
        report_timing -delay_type max -to $endpoints -max_paths 20 -nworst 1 -file [file join $out setup_${family}.rpt]
        report_timing -delay_type min -to $endpoints -max_paths 20 -nworst 1 -file [file join $out hold_${family}.rpt]
    }
}
report_timing -delay_type max -group clk_delay_ref -max_paths 20 -file [file join $out setup_ref200.rpt]
report_timing -delay_type min -group clk_delay_ref -max_paths 20 -file [file join $out hold_ref200.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_clock_interaction -file [file join $out clock_interaction.rpt]
report_exceptions -file [file join $out exceptions.rpt]
report_cdc -details -file [file join $out cdc.rpt]
set required_setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set required_hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "REQUESTED_FCLK=$requested_fclk SETUP=$required_setup HOLD=$required_hold"
set verified_fclk 0
set fd [open [file join $out frequency_timing.csv] w]
puts $fd "FCLK_Hz,setup_slack_ns,hold_slack_ns"
set rates [lsort -integer -unique -decreasing [concat {200000000 180000000 163636364 150000000 138461539 128571429 120000000 100000000} [list $requested_fclk]]]
foreach rate $rates {
    # Do not promote a release above the explicitly implemented work point.
    # Higher-frequency exploration requires a separately authorized build.
    if {$rate>$requested_fclk} {continue}
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
if {!$rtl_debug && ($required_setup<0 || $required_hold<0 || $verified_fclk<$requested_fclk)} {
    error "Release requested FCLK $requested_fclk failed; no downgraded bitstream published (setup=$required_setup hold=$required_hold)"
}
report_clocks -file [file join $out clocks_verified.rpt]
report_utilization -file [file join $out utilization.rpt]
report_utilization -hierarchical -file [file join $out utilization_hier.rpt]
report_timing_summary -report_unconstrained -file [file join $out timing_verified.rpt]
set all_timing [report_timing_summary -return_string]
if {![string match {*All user specified timing constraints are met.*} $all_timing]} {
    error "Routed timing summary includes a failing setup/hold/recovery/removal/pulse-width check"
}
set worst [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]
set hold [get_property SLACK [get_timing_paths -max_paths 1 -delay_type min]]
puts "VERIFIED_SETUP_SLACK=$worst VERIFIED_HOLD_SLACK=$hold"
if {$worst < 0 || $hold < 0} {error "Routed timing failed with all FCLK input sampling paths constrained"}
write_checkpoint -force [file join $out system_wrapper_verified.dcp]
# Generate from this open checkpoint. File timestamps alone do not establish
# the identity of an old bitstream after checkout/copy/restore.
write_bitstream -force [file join $out system_wrapper_verified.bit]
file copy -force [file join $out system_wrapper_verified.bit] [file join $out system_wrapper.bit]
# Publish timing metadata only after bitgen and its DRC succeed. A failed new
# route must not relabel the old bitstream with a new verified clock limit.
set fd [open [file join $out verified_clock.json] w]
puts $fd "{\"FCLK_max_Hz\":$verified_fclk,\"SWCLK_max_Hz\":[expr {$verified_fclk/2}],\"setup_slack_ns\":$worst,\"hold_slack_ns\":$hold,\"requested_FCLK_Hz\":$requested_fclk,\"RTL_DEBUG\":$rtl_debug,\"optional_observation_cells\":[llength $observation_cells],\"formal_product_acceptance\":false}"
close $fd
file mkdir [file join $root build checkpoints]
file copy -force [file join $out system_wrapper_verified.dcp] [file join $root build checkpoints dma_routed_reference.dcp]
puts "VERIFIED_BITSTREAM_READY"
