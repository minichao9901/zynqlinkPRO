# ETM frontend on a dedicated AXI-Lite aperture; existing probe addresses remain.
if {![llength [get_bd_cells -quiet orbtrace_0]]} {
  set_property CONFIG.NUM_MI 7 [get_bd_cells ps7_0_axi_periph]
  create_bd_cell -type module -reference orbtrace_controller orbtrace_0
  connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M06_AXI] [get_bd_intf_pins orbtrace_0/s_axi]
  connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins orbtrace_0/clk]
  connect_bd_net [get_bd_pins rst_ps7_0_50M/peripheral_aresetn] [get_bd_pins orbtrace_0/rst_n]
  connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins ps7_0_axi_periph/M06_ACLK]
  connect_bd_net [get_bd_pins rst_ps7_0_50M/peripheral_aresetn] [get_bd_pins ps7_0_axi_periph/M06_ARESETN]
  create_bd_port -dir I -type clk trace_clk
  create_bd_port -dir I -from 3 -to 0 trace_data
  connect_bd_net [get_bd_ports trace_clk] [get_bd_pins orbtrace_0/trace_clk]
  connect_bd_net [get_bd_ports trace_data] [get_bd_pins orbtrace_0/trace_data]
  assign_bd_address
  set seg [get_bd_addr_segs processing_system7_0/Data/SEG_orbtrace_0_reg0]
  set_property range 64K $seg
  set_property offset 0x40030000 $seg
}
# A stopped target TRACECLK cannot serve IDELAYCTRL calibration. Keep a fixed,
# independent 200 MHz PS reference, unaffected by DAP's FCLK0 rate changes.
set_property -dict [list CONFIG.PCW_EN_CLK1_PORT 1 CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ 200] [get_bd_cells processing_system7_0]
set raw_diag [expr {[info exists ::env(ZYNQLINK_RAW_TRACE)] && $::env(ZYNQLINK_RAW_TRACE) eq "1"}]
if {[lsearch -exact [list_property [get_bd_cells orbtrace_0]] CONFIG.RAW_DIAGNOSTIC] < 0} {
  update_module_reference [get_ips system_orbtrace_0_0]
}
if {[lsearch -exact [list_property [get_bd_cells orbtrace_0]] CONFIG.RAW_DIAGNOSTIC] < 0} {
  error "ORBTrace module reference did not refresh RAW_DIAGNOSTIC parameter"
}
set_property CONFIG.RAW_DIAGNOSTIC $raw_diag [get_bd_cells orbtrace_0]
if {[get_property CONFIG.RAW_DIAGNOSTIC [get_bd_cells orbtrace_0]] != $raw_diag} {
  error "ORBTrace RAW_DIAGNOSTIC configuration did not propagate"
}
puts "ORBTRACE_RAW_DIAGNOSTIC=$raw_diag"
if {![llength [get_bd_pins -quiet orbtrace_0/ref_clk]]} {
  update_module_reference [get_ips system_orbtrace_0_0]
}
if {![llength [get_bd_nets -quiet -of_objects [get_bd_pins orbtrace_0/ref_clk]]]} {
  connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK1] [get_bd_pins orbtrace_0/ref_clk]
}
validate_bd_design
save_bd_design
