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
      # Vivado 2018.3 can return the local name "ref_clk" here. Do not
      # attach the independent 200MHz input to the FCLK0 system bus clock.
      if {$cell eq "etm_ddr_0" && [regexp {(^|/)ref_clk$} [get_property NAME $p]]} {continue}
      if {![llength [get_bd_nets -quiet -of_objects $p]]} {connect_bd_net $ddr_clk $p}
    }
    foreach p [get_bd_pins -of_objects [get_bd_cells $cell] -filter {TYPE == rst && DIR == I}] {
      if {![llength [get_bd_nets -quiet -of_objects $p]]} {connect_bd_net $ddr_rst $p}
    }
  }
  connect_bd_net $ddr_clk [get_bd_pins processing_system7_0/S_AXI_HP1_ACLK]
  # Connect before the first validation (the shared wiring pass is below).
  connect_bd_net [get_bd_pins orbtrace_0/ddr_ref_clk] [get_bd_pins etm_ddr_0/ref_clk]
  assign_bd_address
  set ddr_seg [get_bd_addr_segs processing_system7_0/Data/SEG_etm_ddr_0_reg0]
  set_property range 64K $ddr_seg
  set_property offset 0x40040000 $ddr_seg
  set etm_ddr_changed 1
}
if {$want_etm_ddr} {
  if {![llength [get_bd_pins -quiet etm_ddr_0/ref_clk]] ||
      [lsearch -exact [list_property [get_bd_cells etm_ddr_0]] CONFIG.ENABLE_TRACE_SOURCE]<0} {
    update_module_reference [get_ips system_etm_ddr_0_0]
  }
  set trace_source_supported [expr {$raw_diag==4}]
  if {[get_property CONFIG.ENABLE_TRACE_SOURCE [get_bd_cells etm_ddr_0]] != $trace_source_supported} {
    set_property CONFIG.ENABLE_TRACE_SOURCE $trace_source_supported [get_bd_cells etm_ddr_0]
    set etm_ddr_changed 1
  }
  foreach {from to} {
    orbtrace_0/ddr_ref_clk etm_ddr_0/ref_clk
    orbtrace_0/ddr_ready etm_ddr_0/trace_ready
    orbtrace_0/ddr_idle etm_ddr_0/trace_idle
    orbtrace_0/ddr_receiver_ready_ref etm_ddr_0/trace_receiver_ready_ref
    orbtrace_0/ddr_frame etm_ddr_0/trace_frame
    orbtrace_0/ddr_tail etm_ddr_0/trace_tail
    orbtrace_0/ddr_tail_bytes etm_ddr_0/trace_tail_bytes
    orbtrace_0/ddr_frame_event etm_ddr_0/trace_frame_event
    orbtrace_0/ddr_parser_error etm_ddr_0/trace_parser_error
    orbtrace_0/ddr_sync_event etm_ddr_0/trace_sync_event
    orbtrace_0/ddr_tail_ambiguous etm_ddr_0/trace_tail_ambiguous
    etm_ddr_0/trace_hold orbtrace_0/ddr_hold
    etm_ddr_0/trace_prepare orbtrace_0/ddr_prepare
    etm_ddr_0/trace_sampler_gate orbtrace_0/ddr_sampler_gate
    etm_ddr_0/trace_parser_enable orbtrace_0/ddr_parser_enable
    etm_ddr_0/trace_parser_clear orbtrace_0/ddr_parser_clear
  } {
    set src [get_bd_pins $from];set dst [get_bd_pins $to]
    if {![llength [get_bd_nets -quiet -of_objects $dst]]} {
      connect_bd_net $src $dst
      set etm_ddr_changed 1
    }
  }
}
puts "ETM_DDR_MEMORY_PILOT=$want_etm_ddr"
validate_bd_design
save_bd_design
