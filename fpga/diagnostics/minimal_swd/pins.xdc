set_property -dict {PACKAGE_PIN D20 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 4} [get_ports swclk]
set_property -dict {PACKAGE_PIN D19 IOSTANDARD LVCMOS33 SLEW FAST DRIVE 8 PULLUP true} [get_ports swdio]
set_property -dict {PACKAGE_PIN E19 IOSTANDARD LVCMOS33} [get_ports nreset]
set_property -dict {PACKAGE_PIN E18 IOSTANDARD LVCMOS33} [get_ports ntrst]
create_clock -name clk_fpga_0 -period 10.000 [get_pins {minimal_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]
# Passive pad-edge detector is intentionally asynchronous. The GPIO software
# reads it with the clock stopped. These exceptions never apply to the SWD
# driver or AXI logic; unexpected sub-spec pulses are diagnostic observations.
create_clock -name pad_feedback -period 1000.000 -waveform {0 10} [get_ports swclk]
set_clock_groups -asynchronous -group [get_clocks clk_fpga_0] -group [get_clocks pad_feedback]
