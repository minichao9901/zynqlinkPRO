set root [file normalize [file join [file dirname [info script]] ..]]
open_project [file join $root build fpga_dma_global zynqlink_dma.xpr]
open_bd_design [get_files system.bd]
foreach name {ps7_0_axi_periph dma_bus cmd_bus rsp_bus pkt_bus} {
  foreach cell [concat [get_bd_cells $name] [get_bd_cells -quiet $name/xbar]] {
    foreach prop [list_property $cell] {
      if {[string match *DATA_WIDTH* $prop]} {puts "ACTUAL_AXI_WIDTH $cell $prop=[get_property $prop $cell]"}
    }
  }
}
close_project
