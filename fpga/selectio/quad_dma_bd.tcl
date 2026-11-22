# GP1 owns the debug queue and CDMA control aperture. Only the three
# compatibility BRAM windows retain GP0/FCLK0 sinks on the debug DMA path.
set quad [get_bd_pins sio_clock/quad_clk]
set old_clock [get_bd_pins processing_system7_0/FCLK_CLK0]
set old_reset [get_bd_pins rst_ps7_0_50M/peripheral_aresetn]
create_bd_cell -type ip -vlnv xilinx.com:ip:util_vector_logic:2.0 quad_axi_reset
set_property -dict {CONFIG.C_OPERATION not CONFIG.C_SIZE 1} [get_bd_cells quad_axi_reset]
connect_bd_net [get_bd_pins sio_clock/phy_reset] [get_bd_pins quad_axi_reset/Op1]
set quad_reset [get_bd_pins quad_axi_reset/Res]

proc move_quad_input {pin before after} {
    set target [get_bd_pins $pin]
    set net [get_bd_nets -of_objects $before]
    if {[get_bd_nets -of_objects $target] ne $net} {
        error "$pin was not connected to $before"
    }
    disconnect_bd_net $net $target
    connect_bd_net $after $target
}

delete_bd_objs [get_bd_intf_nets -of_objects [get_bd_intf_pins cdma/S_AXI_LITE]]
set_property -dict {CONFIG.NUM_MI 4 CONFIG.M03_HAS_REGSLICE 4} [get_bd_cells sio_bus]
connect_bd_intf_net [get_bd_intf_pins sio_bus/M03_AXI] [get_bd_intf_pins cdma/S_AXI_LITE]
connect_bd_net $quad [get_bd_pins sio_bus/M03_ACLK]
connect_bd_net $quad_reset [get_bd_pins sio_bus/M03_ARESETN]

foreach pin {
    processing_system7_0/M_AXI_GP1_ACLK processing_system7_0/S_AXI_HP0_ACLK
    sio_bus/ACLK sio_bus/S00_ACLK sio_bus/M00_ACLK sio_bus/M01_ACLK sio_bus/M02_ACLK
    sio_jtag/axi_aclk sio_swd/axi_aclk sio_aux/axi_aclk
    cdma/s_axi_lite_aclk cdma/m_axi_aclk
    dma_bus/ACLK dma_bus/S00_ACLK dma_bus/M00_ACLK dma_bus/M01_ACLK
    dma_bus/M02_ACLK dma_bus/M03_ACLK dma_bus/M04_ACLK
    sio_payload_bram/s_axi_aclk cmd_bus/S01_ACLK rsp_bus/S01_ACLK pkt_bus/S01_ACLK
} {move_quad_input $pin $old_clock $quad}
foreach pin {
    sio_bus/ARESETN sio_bus/S00_ARESETN sio_bus/M00_ARESETN sio_bus/M01_ARESETN sio_bus/M02_ARESETN
    sio_jtag/axi_aresetn sio_swd/axi_aresetn sio_aux/axi_aresetn
    cdma/s_axi_lite_aresetn
    dma_bus/ARESETN dma_bus/S00_ARESETN dma_bus/M00_ARESETN dma_bus/M01_ARESETN
    dma_bus/M02_ARESETN dma_bus/M03_ARESETN dma_bus/M04_ARESETN
    sio_payload_bram/s_axi_aresetn cmd_bus/S01_ARESETN rsp_bus/S01_ARESETN pkt_bus/S01_ARESETN
} {move_quad_input $pin $old_reset $quad_reset}

set_property CONFIG.QUAD_AXI 1 [get_bd_cells swd_controller_0]
set_property CONFIG.SAME_CLOCK 1 [get_bd_cells sio_swd]
assign_bd_address
set_property offset 0x80040000 [get_bd_addr_segs processing_system7_0/Data/SEG_cdma_Reg]
validate_bd_design
save_bd_design
puts "SELECTIO_QUAD_DMA GP1 HP0 CDMA payload SWD regs and worker on quad_clk"
