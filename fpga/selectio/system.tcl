# Add the two AXI transaction queues to the existing USB/DDR/ETM system.
# Keep the main command/DDR and ETM fabric on GP0. The extra engines
# have their own GP1 decoder and register slices.
set ps [get_bd_cells processing_system7_0]
set_property CONFIG.PCW_USE_M_AXI_GP1 1 $ps
set bus [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 sio_bus]
set_property -dict {CONFIG.NUM_SI 1 CONFIG.NUM_MI 3 CONFIG.ENABLE_ADVANCED_OPTIONS 1 CONFIG.XBAR_DATA_WIDTH 32 CONFIG.S00_HAS_REGSLICE 4 CONFIG.M00_HAS_REGSLICE 4 CONFIG.M01_HAS_REGSLICE 4 CONFIG.M02_HAS_REGSLICE 4} $bus
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_GP1] [get_bd_intf_pins $bus/S00_AXI]
connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $ps/M_AXI_GP1_ACLK] [get_bd_pins $bus/ACLK] [get_bd_pins $bus/S00_ACLK]
connect_bd_net [get_bd_pins rst_ps7_0_50M/peripheral_aresetn] [get_bd_pins $bus/ARESETN] [get_bd_pins $bus/S00_ARESETN]
set_property CONFIG.SELECTIO 1 [get_bd_cells swd_controller_0]
set_property CONFIG.SHARED_CALIBRATION 1 [get_bd_cells orbtrace_0]
create_bd_cell -type module -reference selectio_clocking sio_clock
foreach {engine module master offset} {
    sio_jtag jtag200_regs M00 0x80000000
    sio_swd  swd200_regs  M01 0x80010000
    sio_aux selectio_aux_regs M02 0x80020000
} {
    create_bd_cell -type module -reference $module $engine
    connect_bd_intf_net [get_bd_intf_pins $bus/${master}_AXI] [get_bd_intf_pins $engine/S_AXI]
    connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins $engine/axi_aclk] [get_bd_pins $bus/${master}_ACLK]
    connect_bd_net [get_bd_pins rst_ps7_0_50M/peripheral_aresetn] [get_bd_pins $engine/axi_aresetn] [get_bd_pins $bus/${master}_ARESETN]
    set aperture [expr {$engine eq "sio_aux" ? "128K" : "16K"}]
    create_bd_addr_seg -range $aperture -offset $offset [get_bd_addr_spaces processing_system7_0/Data] \
        [get_bd_addr_segs -of_objects [get_bd_intf_pins $engine/S_AXI]] SEG_${engine}
}
set_property CONFIG.ENABLE_BLOCK 1 [get_bd_cells sio_jtag]
foreach pins {
    {orbtrace_0/ddr_ref_clk sio_clock/ref_clk}
    {rst_ps7_0_50M/peripheral_aresetn sio_clock/resetn}
    {orbtrace_0/io_calibrated sio_clock/calibrated sio_jtag/delay_ready sio_swd/delay_ready}
    {sio_clock/serial_clk swd_controller_0/hs_serial_phase}
    {sio_clock/quad_clk sio_swd/word_clk swd_controller_0/hs_quad_phase sio_aux/quad_clk}
    {sio_clock/octet_clk sio_jtag/word_clk swd_controller_0/hs_octet_phase}
    {sio_clock/phy_reset swd_controller_0/hs_reset sio_aux/phy_reset}
    {sio_clock/owner swd_controller_0/hs_owner}
    {sio_clock/jtag_reset sio_jtag/word_reset}
    {sio_clock/jtag_ready sio_jtag/ready}
    {sio_clock/swd_reset sio_swd/word_reset}
    {swd_controller_0/hs_legacy_released sio_clock/legacy_released}
    {sio_aux/monitor_tdi swd_controller_0/hs_monitor_tdi}
    {sio_aux/uart_request swd_controller_0/hs_uart_request}
    {swd_controller_0/hs_uart_grant sio_aux/uart_granted}
    {sio_aux/pad_request sio_clock/aux_request}
    {sio_clock/aux_granted sio_aux/pad_granted}
    {sio_aux/spi_selected swd_controller_0/hs_aux_spi}
    {sio_aux/clock_slots swd_controller_0/hs_aux_sck}
    {sio_aux/select_slots swd_controller_0/hs_aux_cs}
    {sio_aux/tx_slots swd_controller_0/hs_aux_tx}
    {swd_controller_0/hs_aux_rx sio_aux/pad_samples}
    {sio_swd/live_config swd_controller_0/hs_live_config}
    {swd_controller_0/hs_live_jtag sio_clock/live_jtag}
    {swd_controller_0/hs_live_swd sio_clock/live_swd}
    {sio_jtag/phy_hold sio_clock/jtag_hold}
    {sio_swd/hold sio_clock/swd_hold}
    {sio_jtag/lane_word swd_controller_0/hs_jtag_lanes}
    {swd_controller_0/hs_jtag_samples sio_jtag/rx_word}
    {sio_jtag/delay_load swd_controller_0/hs_tdo_load}
    {sio_jtag/delay_value swd_controller_0/hs_tdo_tap}
    {sio_swd/clk_slots swd_controller_0/hs_swd_ckslots}
    {sio_swd/data_slots swd_controller_0/hs_swd_data}
    {sio_swd/release_slots swd_controller_0/hs_swd_release}
    {swd_controller_0/hs_swd_samples sio_swd/rx_slots}
    {sio_swd/delay_load swd_controller_0/hs_swdio_load}
    {sio_swd/delay_value swd_controller_0/hs_swdio_tap}
} {
    set endpoints {}
    foreach pin $pins {lappend endpoints [get_bd_pins $pin]}
    connect_bd_net {*}$endpoints
}
source [file join $root fpga selectio payload_bd.tcl]
validate_bd_design
save_bd_design
