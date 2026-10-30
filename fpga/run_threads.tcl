# Executed inside each Vivado child run; -jobs is a separate process limit.
set task_threads 8
if {[info exists ::env(ZYNQLINK_RUN_THREADS)]} {
    set task_threads $::env(ZYNQLINK_RUN_THREADS)
    if {![string is integer -strict $task_threads] || $task_threads < 1 || $task_threads > 8} {
        error "ZYNQLINK_RUN_THREADS must be an integer from 1 to 8"
    }
}
set_param general.maxThreads $task_threads
puts "ZYNQLINK_RUN_MAX_THREADS=[get_param general.maxThreads]"
