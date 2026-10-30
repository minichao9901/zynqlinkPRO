# ZYNQ Micro-SYS J7 consecutive pins 15..19, board schematic sheet 15_GPIO.
# J7.16 = B35_L13_P / MRCC; J7.14 is nearby GND. All signals LVCMOS33 input.
set_property -dict {PACKAGE_PIN H16 IOSTANDARD LVCMOS33} [get_ports trace_clk]
set_property -dict {PACKAGE_PIN H15 IOSTANDARD LVCMOS33} [get_ports {trace_data[0]}]
set_property -dict {PACKAGE_PIN G15 IOSTANDARD LVCMOS33} [get_ports {trace_data[1]}]
set_property -dict {PACKAGE_PIN H17 IOSTANDARD LVCMOS33} [get_ports {trace_data[2]}]
set_property -dict {PACKAGE_PIN N15 IOSTANDARD LVCMOS33} [get_ports {trace_data[3]}]
# First integration timing envelope: TRACECLK <= 50 MHz, DDR. This constraint
# is a design requirement; physical F103ZE capture still verifies cable margin.
create_clock -name trace_clk -period 20.000 [get_ports trace_clk]
set_input_delay -clock trace_clk -max 3.000 [get_ports {trace_data[*]}]
set_input_delay -clock trace_clk -min 0.500 [get_ports {trace_data[*]}]
set_input_delay -clock trace_clk -clock_fall -add_delay -max 3.000 [get_ports {trace_data[*]}]
set_input_delay -clock trace_clk -clock_fall -add_delay -min 0.500 [get_ports {trace_data[*]}]
set_clock_groups -asynchronous -group [get_clocks trace_clk] -group [get_clocks clk_fpga_0]
create_clock -name clk_delay_ref -period 5.000 [get_pins {system_i/processing_system7_0/inst/PS7_i/FCLKCLK[1]}]
set_clock_groups -asynchronous -group [get_clocks clk_delay_ref] -group [get_clocks clk_fpga_0]
