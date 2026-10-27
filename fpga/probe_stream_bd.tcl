# Dedicated PL packet memory accessible to both PS descriptors and shared CDMA.
# Idempotent so incremental builds keep existing IP checkpoints.
if {![llength [get_bd_cells -quiet pkt_mem]]} {
    set_property CONFIG.NUM_MI 6 [get_bd_cells ps7_0_axi_periph]
    set_property CONFIG.NUM_MI 4 [get_bd_cells dma_bus]
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_bram_ctrl:4.1 pkt_mem
    set_property -dict [list CONFIG.DATA_WIDTH 32 CONFIG.SINGLE_PORT_BRAM 1 CONFIG.SUPPORTS_NARROW_BURST 0] [get_bd_cells pkt_mem]
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 pkt_bus
    set_property -dict [list CONFIG.NUM_SI 2 CONFIG.NUM_MI 1 CONFIG.XBAR_DATA_WIDTH 32] [get_bd_cells pkt_bus]
    connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M05_AXI] [get_bd_intf_pins pkt_bus/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins dma_bus/M03_AXI] [get_bd_intf_pins pkt_bus/S01_AXI]
    connect_bd_intf_net [get_bd_intf_pins pkt_bus/M00_AXI] [get_bd_intf_pins pkt_mem/S_AXI]
    foreach {a c} {clk clk rst rst en en we we addr addr wrdata wrdata rddata rddata} {
        connect_bd_net [get_bd_pins pkt_mem/bram_${a}_a] [get_bd_pins swd_controller_0/pkt_bram_${c}]
    }
    set clk [get_bd_pins processing_system7_0/FCLK_CLK0]
    set rst [get_bd_pins rst_ps7_0_50M/peripheral_aresetn]
    foreach cell {pkt_mem pkt_bus ps7_0_axi_periph dma_bus} {
        foreach p [get_bd_pins -of_objects [get_bd_cells $cell] -filter {TYPE == clk && DIR == I}] {
            if {![llength [get_bd_nets -quiet -of_objects $p]]} {connect_bd_net $clk $p}
        }
        foreach p [get_bd_pins -of_objects [get_bd_cells $cell] -filter {TYPE == rst && DIR == I}] {
            if {![llength [get_bd_nets -quiet -of_objects $p]]} {connect_bd_net $rst $p}
        }
    }
    assign_bd_address
    foreach space {processing_system7_0/Data cdma/Data} {
        set seg [get_bd_addr_segs ${space}/SEG_pkt_mem_Mem0]
        set_property range 32K $seg
        set_property offset 0x42020000 $seg
    }
    validate_bd_design
    save_bd_design
}
