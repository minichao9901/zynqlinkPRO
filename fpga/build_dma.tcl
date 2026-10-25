set root [file normalize [file join [file dirname [info script]] ..]]
set ::zynqlink_no_pipeline [expr {[lsearch -exact $argv --no-pipeline] >= 0}]
set out [file join $root build fpga_dma_global]
if {[file exists [file join $out zynqlink_dma.xpr]] && [lsearch -exact $argv --recreate] < 0} {
    source [file join $root fpga build_incremental.tcl]
    exit
}
create_project -force zynqlink_dma $out -part xc7z020clg400-2
set_param general.maxThreads 8
set_property target_language Verilog [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
add_files [glob [file join $root fpga rtl *.v]]
add_files -fileset constrs_1 [file join $root fpga constraints dap_pins.xdc]
set_property PROCESSING_ORDER LATE [get_files dap_pins.xdc]
source [file join $root fpga bd legacy_system.tcl]
set ps [get_bd_cells processing_system7_0]
set_property -dict [list CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ps
set periph [get_bd_cells ps7_0_axi_periph]
set_property CONFIG.NUM_MI 5 $periph
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_cdma:4.1 cdma
set_property -dict [list CONFIG.C_INCLUDE_SG {0} CONFIG.C_M_AXI_DATA_WIDTH {32} CONFIG.C_M_AXI_MAX_BURST_LEN {64} CONFIG.C_INCLUDE_DRE {0}] [get_bd_cells cdma]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 dma_bus
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {3}] [get_bd_cells dma_bus]
foreach b {cmd rsp} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_bram_ctrl:4.1 ${b}_mem
    set_property -dict [list CONFIG.DATA_WIDTH {32} CONFIG.SINGLE_PORT_BRAM {1} CONFIG.SUPPORTS_NARROW_BURST {0}] [get_bd_cells ${b}_mem]
    foreach {a c} {clk clk rst rst en en we we addr addr wrdata wrdata rddata rddata} {
        connect_bd_net [get_bd_pins ${b}_mem/bram_${a}_a] [get_bd_pins swd_controller_0/${b}_bram_${c}]
    }
}
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M02_AXI] [get_bd_intf_pins cdma/S_AXI_LITE]
# Both CPU and CDMA can access each window; CPU is primarily for diagnostics.
foreach {b idx} {cmd 03 rsp 04} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 ${b}_bus
    set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] [get_bd_cells ${b}_bus]
    connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M${idx}_AXI] [get_bd_intf_pins ${b}_bus/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins ${b}_bus/M00_AXI] [get_bd_intf_pins ${b}_mem/S_AXI]
}
connect_bd_intf_net [get_bd_intf_pins cdma/M_AXI] [get_bd_intf_pins dma_bus/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins dma_bus/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP0]
connect_bd_intf_net [get_bd_intf_pins dma_bus/M01_AXI] [get_bd_intf_pins cmd_bus/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins dma_bus/M02_AXI] [get_bd_intf_pins rsp_bus/S01_AXI]
set clk [get_bd_pins processing_system7_0/FCLK_CLK0]
set rst [get_bd_pins rst_ps7_0_50M/peripheral_aresetn]
foreach cell {cdma dma_bus cmd_mem rsp_mem cmd_bus rsp_bus ps7_0_axi_periph} {
    foreach p [get_bd_pins -of_objects [get_bd_cells $cell] -filter {TYPE == clk && DIR == I}] {
        if {![llength [get_bd_nets -quiet -of_objects $p]]} {connect_bd_net $clk $p}
    }
    foreach p [get_bd_pins -of_objects [get_bd_cells $cell] -filter {TYPE == rst && DIR == I}] {
        if {![llength [get_bd_nets -quiet -of_objects $p]]} {connect_bd_net $rst $p}
    }
}
connect_bd_net $clk [get_bd_pins processing_system7_0/S_AXI_HP0_ACLK]
assign_bd_address
set_property offset 0x40020000 [get_bd_addr_segs processing_system7_0/Data/SEG_cdma_Reg]
foreach {b addr} {cmd 0x42000000 rsp 0x42010000} {
    foreach space {processing_system7_0/Data cdma/Data} {
        set seg [get_bd_addr_segs -quiet ${space}/SEG_${b}_mem_Mem0]
        if {[llength $seg]} {set_property range 4K $seg; set_property offset $addr $seg}
    }
}
validate_bd_design
save_bd_design
source [file join $root fpga axi_pipeline.tcl]
write_bd_tcl -force [file join $out system_dma.tcl]
set_property synth_checkpoint_mode Hierarchical [get_files system.bd]
generate_target all [get_files system.bd]
make_wrapper -files [get_files system.bd] -top
add_files [file join $out zynqlink_dma.srcs sources_1 bd system hdl system_wrapper.v]
set_property top system_wrapper [current_fileset]
source [file join $root fpga configure_runs.tcl]
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {error "Synthesis failed"}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "Implementation failed"}
source [file join $root fpga verify_routed.tcl]
puts "DMA_BITSTREAM_READY $out/system_wrapper.bit"
