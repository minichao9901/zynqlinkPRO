# Preserve the connector pin names while moving GPIO IOBUFs into the protocol
# mux: B19=TDI, A20=TDO, E19=nRESET, E18=optional nTRST.
if {[llength [get_bd_intf_ports -quiet gpio_rtl_0]]} {
    set nets [get_bd_intf_nets -quiet -of_objects [get_bd_intf_ports gpio_rtl_0]]
    if {[llength $nets]} {delete_bd_objs $nets}
    delete_bd_objs [get_bd_intf_ports gpio_rtl_0]
}
if {![llength [get_bd_ports -quiet gpio_rtl_0_tri_io]]} {
    create_bd_port -dir IO -from 3 -to 0 gpio_rtl_0_tri_io
    connect_bd_net [get_bd_ports gpio_rtl_0_tri_io] [get_bd_pins swd_controller_0/gpio_aux]
    connect_bd_net [get_bd_pins axi_gpio_0/gpio_io_o] [get_bd_pins swd_controller_0/gpio_out]
    connect_bd_net [get_bd_pins axi_gpio_0/gpio_io_t] [get_bd_pins swd_controller_0/gpio_tri]
    connect_bd_net [get_bd_pins axi_gpio_0/gpio_io_i] [get_bd_pins swd_controller_0/gpio_in]
}
validate_bd_design
save_bd_design
# The old generated wrapper contains its own GPIO IOBUFs. Regenerate it so
# each physical pad has exactly one IOBUF, now inside swd_controller.
make_wrapper -files [get_files system.bd] -top
