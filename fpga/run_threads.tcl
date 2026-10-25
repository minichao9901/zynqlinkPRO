# Executed inside each Vivado child run; -jobs is a separate process limit.
set_param general.maxThreads 8
puts "ZYNQLINK_RUN_MAX_THREADS=[get_param general.maxThreads]"
