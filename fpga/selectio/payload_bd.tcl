# CDMA needs a burst-capable payload aperture. Control and status stay on GP1.
create_bd_cell -type module -reference selectio_payload_ram sio_payload
set_property CONFIG.SELECTIO_SLICE $slice [get_bd_cells sio_payload]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_bram_ctrl:4.1 sio_payload_bram
set_property -dict {CONFIG.DATA_WIDTH 32 CONFIG.SINGLE_PORT_BRAM 1 CONFIG.SUPPORTS_NARROW_BURST 0} [get_bd_cells sio_payload_bram]
set_property CONFIG.NUM_MI 5 [get_bd_cells dma_bus]
connect_bd_intf_net [get_bd_intf_pins dma_bus/M04_AXI] [get_bd_intf_pins sio_payload_bram/S_AXI]
foreach {src dst} {clk clk rst rst en en we we addr addr wrdata wdata rddata rdata} {
    connect_bd_net [get_bd_pins sio_payload_bram/bram_${src}_a] [get_bd_pins sio_payload/host_${dst}]
}
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins dma_bus/M04_ACLK] [get_bd_pins sio_payload_bram/s_axi_aclk]
connect_bd_net [get_bd_pins rst_ps7_0_50M/peripheral_aresetn] [get_bd_pins dma_bus/M04_ARESETN] [get_bd_pins sio_payload_bram/s_axi_aresetn]
foreach {engine clock} {jtag octet_clk swd quad_clk} {
    connect_bd_net [get_bd_pins sio_clock/$clock] [get_bd_pins sio_payload/${engine}_clk]
    foreach pin {tx_addr tx_data rx_addr rx_data rx_write} {
        connect_bd_net [get_bd_pins sio_${engine}/payload_$pin] [get_bd_pins sio_payload/${engine}_$pin]
    }
}
create_bd_addr_seg -range 16K -offset 0x45000000 [get_bd_addr_spaces cdma/Data] [get_bd_addr_segs sio_payload_bram/S_AXI/Mem0] SEG_selectio_payload
