# Reuse the project/IP cache. Never recreate the BD for routine RTL edits.
set root [file normalize [file join [file dirname [info script]] ..]]
set ::zynqlink_no_pipeline [expr {[lsearch -exact $argv --no-pipeline] >= 0}]
set out [file join $root build fpga_dma_global]
open_project [file join $out zynqlink_dma.xpr]
source [file join $root fpga configure_ip_cache.tcl]
set_param general.maxThreads 8
set impl_only [expr {[lsearch -exact $argv --impl-only] >= 0}]
set rtl_stamp [exec python [file join $root tools fpga_rtl_stamp.py]]
set stamp_file [file join $out swd_rtl_built.stamp]
set old_stamp {}
if {[file exists $stamp_file]} {
    set fd [open $stamp_file r]; set old_stamp [read $fd]; close $fd
}
if {$impl_only && $rtl_stamp ne $old_stamp} {
    error "RTL differs from synthesized checkpoint; rerun without --impl-only"
}
set fresh_impl [expr {[lsearch -exact $argv --fresh] >= 0}]
set_property PROCESSING_ORDER LATE [get_files dap_pins.xdc]
if {!$impl_only} {
    # The first switch from the initial global run creates the IP DCP cache;
    # subsequent builds retain unchanged IPs, including CDMA and interconnects.
    set_property synth_checkpoint_mode Hierarchical [get_files system.bd]
    open_bd_design [get_files system.bd]
    # New helper RTL files must be added to the module-reference source set
    # explicitly; Vivado 2018.3 does not discover them from the old XCI.
    set packet_rtl [file join $root fpga rtl dap_transfer_block_engine.v]
    if {[file exists $packet_rtl]} {add_files -norecurse $packet_rtl}
    add_files -norecurse [file join $root fpga rtl probe_sample_engine.v]
    add_files -norecurse [file join $root fpga rtl probe_rtt_engine.v]
    add_files -norecurse [file join $root fpga rtl probe_stream_engine.v]
    source [file join $root fpga axi_pipeline.tcl]
    if {$axi_pipeline_changed} {set fresh_impl 1}
    # Vivado 2018.3 does not reliably invalidate an OOC module-reference
    # checkpoint when its external RTL changes. Refresh only that block.
    if {$rtl_stamp ne $old_stamp} {
        # Internal-only edits need an OOC reset, not a BD topology upgrade.
        # The new BRAM pins are the sole interface change in this branch.
        if {![llength [get_bd_pins -quiet swd_controller_0/pkt_bram_en]] ||
            ![llength [get_bd_cells -quiet pkt_mem]]} {
            update_module_reference [get_ips system_swd_controller_0_0]
            source [file join $root fpga probe_stream_bd.tcl]
            save_bd_design
        }
        # update_module_reference invalidates its nested products itself;
        # reset_target on the nested XCI is forbidden in Vivado 2018.3.
        set swd_run [get_runs -quiet system_swd_controller_0_0_synth_1]
        if {[llength $swd_run]} {reset_run $swd_run}
        reset_run synth_1
    }
    generate_target all [get_files system.bd]
    update_compile_order -fileset sources_1
    source [file join $root fpga configure_runs.tcl]
    if {[get_property NEEDS_REFRESH [get_runs synth_1]] || [get_property PROGRESS [get_runs synth_1]] != "100%"} {
        reset_run synth_1
        launch_runs synth_1 -jobs 4
        wait_on_run synth_1
    }
    if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {error "Synthesis failed"}
    if {$rtl_stamp ne [exec python [file join $root tools fpga_rtl_stamp.py]]} {
        error "RTL changed during synthesis; rebuild before implementation"
    }
    set fd [open $stamp_file w]; puts -nonewline $fd $rtl_stamp; close $fd
}
set ref [file join $root build checkpoints dma_routed_reference.dcp]
source [file join $root fpga configure_runs.tcl]
set verified_bit [file join $out system_wrapper_verified.bit]
set routed_dcp [file join $out zynqlink_dma.runs impl_1 system_wrapper_routed.dcp]
if {!$fresh_impl && ![get_property NEEDS_REFRESH [get_runs impl_1]] &&
    [get_property PROGRESS [get_runs impl_1]] == "100%" &&
    [file exists $verified_bit] && [file exists $routed_dcp] &&
    [file mtime $verified_bit] >= [file mtime $routed_dcp]} {
    puts "FPGA_UP_TO_DATE: existing verified bitstream retained"
    return
}
reset_run impl_1
if {!$fresh_impl && [file exists $ref]} {
    set_property INCREMENTAL_CHECKPOINT $ref [get_runs impl_1]
    puts "INCREMENTAL_IMPLEMENTATION_REFERENCE=$ref"
} else {
    set_property INCREMENTAL_CHECKPOINT {} [get_runs impl_1]
    set_property strategy Performance_Explore [get_runs impl_1]
}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "Implementation failed"}
if {[catch {source [file join $root fpga verify_routed.tcl]} timing_error]} {
    if {$fresh_impl || (![string match {*Routed timing failed*} $timing_error] &&
                       ![string match {*write_bitstream*} $timing_error])} {error $timing_error}
    # A changed timing-critical block may not fit the reference placement.
    # Reuse every synthesis DCP, but allow a fresh implementation once.
    # Incremental routing can also leave partial antennas that only bitgen's
    # DRC rejects. Never suppress DRC: retry fresh once, then propagate failure.
    puts "INCREMENTAL_VERIFICATION_FAILED: $timing_error; retrying fresh placement with cached synthesis"
    close_design
    reset_run impl_1
    set_property INCREMENTAL_CHECKPOINT {} [get_runs impl_1]
    set_property strategy Performance_Explore [get_runs impl_1]
    launch_runs impl_1 -to_step route_design -jobs 4
    wait_on_run impl_1
    if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "Implementation failed"}
    source [file join $root fpga verify_routed.tcl]
}
