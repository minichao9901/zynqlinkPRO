#-----------------------------------------------------------------------------
# SWD / GPIO pin constraints for system_wrapper
# Notes:
# 1. The PL fabric clock driving swd_controller comes from PS FCLK and is
#    constrained by the block design / PS generated constraints.
# 2. This file intentionally keeps only board pin / IO electrical constraints.
#    Old MMCM / BUFGCTRL / CDC exceptions were removed because the current RTL
#    no longer contains those clock domains.
#-----------------------------------------------------------------------------

# GPIO
set_property -dict {PACKAGE_PIN B19 IOSTANDARD LVCMOS33 SLEW FAST DRIVE 8} [get_ports {gpio_rtl_0_tri_io[0]}]
set_property -dict {PACKAGE_PIN A20 IOSTANDARD LVCMOS33} [get_ports {gpio_rtl_0_tri_io[1]}]
set_property -dict {PACKAGE_PIN E19 IOSTANDARD LVCMOS33} [get_ports {gpio_rtl_0_tri_io[2]}]
set_property -dict {PACKAGE_PIN E18 IOSTANDARD LVCMOS33} [get_ports {gpio_rtl_0_tri_io[3]}]

# SWD interface
set_property -dict {PACKAGE_PIN D20 IOSTANDARD LVCMOS33 SLEW FAST DRIVE 8} [get_ports swclk_0]
set_property PACKAGE_PIN D19 [get_ports swdio_0]
set_property IOSTANDARD LVCMOS33 [get_ports swdio_0]
set_property PULLUP true [get_ports swdio_0]
set_property SLEW FAST [get_ports swdio_0]
set_property DRIVE 8 [get_ports swdio_0]

# Production target: FCLK 120 MHz -> SWCLK 60 MHz. Place/route for the
# frequency actually used by this branch; verify_routed still checks both
# setup and hold and records the routed design's safe upper bound.
create_clock -name clk_fpga_0 -period 8.333333 [get_pins {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[0]}]


# Input sampling uses FCLK directly; no gated SWCLK clock domain remains.
