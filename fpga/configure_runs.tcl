set hook [file join [file dirname [info script]] run_threads.tcl]
set ::zynqlink_jobs 4
if {[info exists ::env(ZYNQLINK_RUN_JOBS)]} {
    set ::zynqlink_jobs $::env(ZYNQLINK_RUN_JOBS)
    if {![string is integer -strict $::zynqlink_jobs] || $::zynqlink_jobs < 1 || $::zynqlink_jobs > 4} {
        error "ZYNQLINK_RUN_JOBS must be an integer from 1 to 4"
    }
}
foreach run [get_runs -filter {IS_SYNTHESIS}] {
    set_property STEPS.SYNTH_DESIGN.TCL.PRE $hook $run
}
foreach run [get_runs -filter {IS_IMPLEMENTATION}] {
    if {[info exists ::env(ZYNQLINK_SELECTIO)] && $::env(ZYNQLINK_SELECTIO)==1} {
        set_property STEPS.PLACE_DESIGN.TCL.PRE [file join [file dirname [info script]] selectio j7_pins.tcl] $run
    }
    set_property STEPS.INIT_DESIGN.TCL.PRE $hook $run
    set_property STEPS.OPT_DESIGN.TCL.PRE [file join [file dirname [info script]] probe_io_timing.tcl] $run
}

if {[info exists ::env(ZYNQLINK_SELECTIO)] && $::env(ZYNQLINK_SELECTIO)==1} {
    set run [get_runs impl_1]
    set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE Explore $run
    set_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED true $run
    set_property STEPS.PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore $run
    set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Explore $run
}
