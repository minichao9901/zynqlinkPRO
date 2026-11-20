# RAW4 optimizes away the TRACECLK BUFIO whose shape requires a clock-capable pad.
# Rebind only after opt_design, just as in the main J7 checkpoint flow.
set j7_pads {swclk_0 L15 swdio_0 L16 gpio_rtl_0_tri_io[0] M15
        gpio_rtl_0_tri_io[1] L14 gpio_rtl_0_tri_io[2] M14 gpio_rtl_0_tri_io[3] N15
        trace_clk J16 trace_data[0] K16 trace_data[1] M18 trace_data[2] M17 trace_data[3] L17}
foreach {port ball} $j7_pads {reset_property PACKAGE_PIN [get_ports $port]}
foreach {port ball} $j7_pads {set_property PACKAGE_PIN $ball [get_ports $port]}
set_property -dict {DRIVE 8 SLEW FAST} [get_ports swclk_0]
