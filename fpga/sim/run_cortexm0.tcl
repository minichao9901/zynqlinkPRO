set root [file normalize [file join [file dirname [info script]] ../..]]
set model [lindex $argv 0]
if {$model eq ""} {
    set model E:/Share/github/ZYNQ7020_YuanZi/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.srcs/sim_1/imports/cortexm0
}
set out [file join $root build cortexm0_sim]
if {[file exists [file join $out cortexm0_sim.xpr]]} {
    open_project [file join $out cortexm0_sim.xpr]
} else {
    create_project cortexm0_sim $out -part xc7z020clg400-2
}
set_property target_simulator XSim [current_project]
foreach f {swd_core.v probe_sample_engine.v probe_rtt_engine.v probe_stream_engine.v swd_controller.v swd_batch_engine.v dap_transfer_block_engine.v jtag_shift.v jtag_core.v} {
    add_files -fileset sim_1 [file join $root fpga rtl $f]
}
foreach f {xpm_memory_tdpram.sv tb_packet_axi.sv tb_cortexm0_link.sv} {
    add_files -fileset sim_1 [file join $root fpga sim $f]
}
foreach f {swd_cortexm0_target.v CORTEXM0INTEGRATION.v cortexm0ds_logic.v} {
    add_files -fileset sim_1 [file join $model $f]
}
set_property top tb_cortexm0_link [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
launch_simulation -step compile
launch_simulation -step elaborate
exit
