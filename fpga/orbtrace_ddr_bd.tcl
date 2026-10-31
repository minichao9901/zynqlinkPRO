# Optional DDR path pilot on HP1; legacy ETM and HP0 command DMA remain distinct.
set want_etm_ddr 0
if {[info exists ::env(ZYNQLINK_ETM_DDR)]} {
  if {$::env(ZYNQLINK_ETM_DDR) ni {0 1}} {error "ZYNQLINK_ETM_DDR must be 0 or 1"}
  set want_etm_ddr $::env(ZYNQLINK_ETM_DDR)
}
set etm_ddr_changed 0
if {!$want_etm_ddr && [llength [get_bd_cells -quiet etm_ddr_0]]} {
  delete_bd_objs [get_bd_cells etm_ddr_bus] [get_bd_cells etm_ddr_0]
  set_property CONFIG.NUM_MI 7 [get_bd_cells ps7_0_axi_periph]
  set_property CONFIG.PCW_USE_S_AXI_HP1 0 [get_bd_cells processing_system7_0]
  set etm_ddr_changed 1
}
if {$want_etm_ddr && ![llength [get_bd_cells -quiet etm_ddr_0]]} {
  set_property -dict [list CONFIG.PCW_USE_S_AXI_HP1 1 CONFIG.PCW_S_AXI_HP1_DATA_WIDTH 64] [get_bd_cells processing_system7_0]
  set_property CONFIG.NUM_MI 8 [get_bd_cells ps7_0_axi_periph]
  create_bd_cell -type module -reference orbtrace_ddr_controller etm_ddr_0
  create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 etm_ddr_bus
  set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1 CONFIG.ENABLE_ADVANCED_OPTIONS 1 CONFIG.XBAR_DATA_WIDTH 64 CONFIG.S00_HAS_REGSLICE 4 CONFIG.M00_HAS_REGSLICE 4] [get_bd_cells etm_ddr_bus]
  connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M07_AXI] [get_bd_intf_pins etm_ddr_0/s_axi]
  connect_bd_intf_net [get_bd_intf_pins etm_ddr_0/m_axi] [get_bd_intf_pins etm_ddr_bus/S00_AXI]
  connect_bd_intf_net [get_bd_intf_pins etm_ddr_bus/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP1]
  set ddr_clk [get_bd_pins processing_system7_0/FCLK_CLK0]
  set ddr_rst [get_bd_pins rst_ps7_0_50M/peripheral_aresetn]
  foreach cell {etm_ddr_0 etm_ddr_bus ps7_0_axi_periph} {
    foreach p [get_bd_pins -of_objects [get_bd_cells $cell] -filter {TYPE == clk && DIR == I}] {
      if {![llength [get_bd_nets -quiet -of_objects $p]]} {connect_bd_net $ddr_clk $p}
    }
    foreach p [get_bd_pins -of_objects [get_bd_cells $cell] -filter {TYPE == rst && DIR == I}] {
      if {![llength [get_bd_nets -quiet -of_objects $p]]} {connect_bd_net $ddr_rst $p}
    }
  }
  connect_bd_net $ddr_clk [get_bd_pins processing_system7_0/S_AXI_HP1_ACLK]
  assign_bd_address
  set ddr_seg [get_bd_addr_segs processing_system7_0/Data/SEG_etm_ddr_0_reg0]
  set_property range 64K $ddr_seg
  set_property offset 0x40040000 $ddr_seg
  set etm_ddr_changed 1
}
puts "ETM_DDR_MEMORY_PILOT=$want_etm_ddr"
validate_bd_design
save_bd_design
