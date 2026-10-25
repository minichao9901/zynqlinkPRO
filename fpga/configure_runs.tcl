set hook [file join [file dirname [info script]] run_threads.tcl]
foreach run [get_runs -filter {IS_SYNTHESIS}] {
    set_property STEPS.SYNTH_DESIGN.TCL.PRE $hook $run
}
foreach run [get_runs -filter {IS_IMPLEMENTATION}] {
    set_property STEPS.INIT_DESIGN.TCL.PRE $hook $run
}
