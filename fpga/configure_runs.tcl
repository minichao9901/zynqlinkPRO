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
    set_property STEPS.INIT_DESIGN.TCL.PRE $hook $run
    set_property STEPS.OPT_DESIGN.TCL.PRE [file join [file dirname [info script]] probe_io_timing.tcl] $run
}
