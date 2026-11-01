set ::zynqlink_verify_checkpoint E:/zynqlinkPRO/build/fclk-resume-20261101/final-routed-150.dcp
set ::zynqlink_verify_out E:/zynqlinkPRO/build/fclk-resume-20261101/release-133
file mkdir $::zynqlink_verify_out
source E:/zynqlinkPRO/fpga/verify_routed.tcl
