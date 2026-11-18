# Standalone SWD layout: PS7 GP0, one AXI register bank, and two serial pads.
set source_dir [file dirname [file normalize [info script]]]
set root [file normalize [file join $source_dir ../../..]]
set out [file join $root build swd200 fpga]
file mkdir $out
source [file join $root fpga diagnostics minimal_swd ps7_config.tcl]
create_project -force swd200 $out -part xc7z020clg400-2
set_param general.maxThreads 8
set_property target_language Verilog [current_project]
foreach name {swd200_regs swd200_batch swd200_link swd200_segment swd200_phy} {
    add_files [file join $source_dir $name.v]
}
add_files -fileset constrs_1 [list [file join $source_dir pins.xdc] [file join $source_dir timing.xdc]]
set_property -dict {PROCESSING_ORDER LATE USED_IN_SYNTHESIS false} [get_files timing.xdc]

create_bd_design swd200_bd
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0]
set fd [open [file join $root fpga bd legacy_system.tcl] r]
set declared [regexp -all -inline {CONFIG\.[A-Z0-9_]+} [read $fd]]
close $fd
set writable {}
foreach {key value} $ps7_config {
    if {$key in $declared} {lappend writable $key $value}
}
set_property -dict $writable $ps
set_property -dict [list \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ 133.333333 \
    CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ 50 CONFIG.PCW_FPGA_FCLK1_ENABLE 1 CONFIG.PCW_EN_CLK1_PORT 1 CONFIG.PCW_FCLK_CLK1_BUF TRUE \
    CONFIG.PCW_FPGA2_PERIPHERAL_FREQMHZ 200 CONFIG.PCW_FPGA_FCLK2_ENABLE 1 CONFIG.PCW_EN_CLK2_PORT 1 CONFIG.PCW_FCLK_CLK2_BUF TRUE \
    CONFIG.PCW_USE_M_AXI_GP0 1 CONFIG.PCW_USE_M_AXI_GP1 0 \
    CONFIG.PCW_USE_S_AXI_HP0 0 CONFIG.PCW_USE_S_AXI_HP1 0 CONFIG.PCW_USE_S_AXI_HP2 0 CONFIG.PCW_USE_S_AXI_HP3 0 \
    CONFIG.PCW_USE_S_AXI_ACP 0 CONFIG.PCW_USE_S_AXI_GP0 0 CONFIG.PCW_USE_S_AXI_GP1 0] $ps
foreach {name value} {one 1 zero 0} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 $name
    set_property CONFIG.CONST_VAL $value [get_bd_cells $name]
}
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_bus
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1] [get_bd_cells axi_bus]
create_bd_cell -type module -reference swd200_regs regs
create_bd_cell -type module -reference swd200_phy phy

create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 DDR
create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 FIXED_IO
foreach interface {DDR FIXED_IO} {
    connect_bd_intf_net [get_bd_intf_ports $interface] [get_bd_intf_pins $ps/$interface]
}
connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_GP0] [get_bd_intf_pins axi_bus/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_bus/M00_AXI] [get_bd_intf_pins regs/S_AXI]
set clock [get_bd_pins $ps/FCLK_CLK0]
foreach pin {processing_system7_0/M_AXI_GP0_ACLK axi_bus/ACLK axi_bus/S00_ACLK axi_bus/M00_ACLK reset/slowest_sync_clk regs/axi_aclk phy/axi_aclk} {
    connect_bd_net $clock [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins $ps/FCLK_CLK1] [get_bd_pins phy/fclk_ref]
connect_bd_net [get_bd_pins $ps/FCLK_CLK2] [get_bd_pins phy/delay_ref]
connect_bd_net [get_bd_pins $ps/FCLK_RESET0_N] [get_bd_pins reset/ext_reset_in]
connect_bd_net [get_bd_pins one/dout] [get_bd_pins reset/dcm_locked] [get_bd_pins reset/aux_reset_in]
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins reset/mb_debug_sys_rst]
foreach pin {axi_bus/ARESETN axi_bus/S00_ARESETN axi_bus/M00_ARESETN} {
    connect_bd_net [get_bd_pins reset/interconnect_aresetn] [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins reset/peripheral_aresetn] [get_bd_pins regs/axi_aresetn] [get_bd_pins phy/axi_aresetn]
foreach pin {word_clk word_reset hold delay_ready delay_value delay_load clk_slots data_slots release_slots rx_slots} {
    connect_bd_net [get_bd_pins regs/$pin] [get_bd_pins phy/$pin]
}
foreach {pin direction} {swclk O swdio IO nsrst O} {
    create_bd_port -dir $direction $pin
    connect_bd_net [get_bd_ports $pin] [get_bd_pins phy/$pin]
}
assign_bd_address
set segment [get_bd_addr_segs -of_objects [get_bd_addr_spaces $ps/Data]]
if {[llength $segment] != 1} {error "Expected one GP0 peripheral: $segment"}
set_property offset 0x40000000 $segment
set_property range 16K $segment
validate_bd_design
if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells reset]] != 0} {
    error "PS FCLK_RESET0_N must propagate an active-low reset"
}
foreach {index required} {0 133.333333 1 50 2 200} {
    set actual [get_property CONFIG.PCW_ACT_FPGA${index}_PERIPHERAL_FREQMHZ $ps]
    if {abs($actual - $required) > 0.001} {error "FCLK$index is $actual MHz, expected $required"}
}
if {[get_property CONFIG.PCW_IOPLL_CTRL_FBDIV $ps] != 48} {error "Expected IO PLL feedback divisor 48"}
save_bd_design
set bd [get_files swd200_bd.bd]
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
set_property top swd200_bd_wrapper [current_fileset]
update_compile_order -fileset sources_1

launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {error "SWD200 synthesis failed"}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "SWD200 routing failed"}
open_run impl_1
foreach {clock expected} {clk_fpga_0 7.500 clk_fpga_1 20.000 clk_fpga_2 5.000 serial_raw 5.000 word_raw 10.000} {
    set node [get_clocks $clock]
    if {[llength $node] != 1 || abs([get_property PERIOD $node] - $expected) > 0.002} {
        error "Missing or incorrect clock constraint for $clock"
    }
}
report_timing_summary -report_unconstrained -file [file join $out timing.rpt]
report_io -file [file join $out io.rpt]
report_clocks -file [file join $out clocks.rpt]
report_cdc -details -file [file join $out cdc.rpt]
report_utilization -file [file join $out utilization.rpt]
report_route_status -file [file join $out route.rpt]
report_drc -file [file join $out drc.rpt]
set setup [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]
set hold [get_property SLACK [get_timing_paths -max_paths 1 -delay_type min]]
if {$setup eq "" || $hold eq "" || $setup < 0 || $hold < 0} {
    error "SWD200 timing failed: setup=$setup hold=$hold"
}
foreach {primitive count} {OSERDESE2 2 ISERDESE2 1 IDELAYE2 1 IDELAYCTRL 1 IOBUF 1 MMCME2_ADV 1} {
    if {[llength [get_cells -hier -filter "REF_NAME == $primitive"]] != $count} {
        error "Expected $count routed $primitive instances"
    }
}
foreach {port pin direction} {swclk L15 OUT swdio L16 INOUT nsrst M14 OUT} {
    set pad [get_ports $port]
    if {[get_property PACKAGE_PIN $pad] ne $pin || [get_property DIRECTION $pad] ne $direction} {
        error "Wrong routed pin or direction for $port"
    }
}
set user_ports [lsort [get_property NAME [get_ports -filter {NAME !~ DDR* && NAME !~ FIXED_IO*}]]]
if {$user_ports ne {nsrst swclk swdio}} {error "Unexpected PL pins: $user_ports"}
write_bitstream -force [file join $out probe.bit]
set init [glob -nocomplain [file join $out swd200.srcs sources_1 bd swd200_bd ip *processing_system7* ps7_init.tcl]]
if {[llength $init] != 1} {error "Missing generated PS init: $init"}
file copy -force [lindex $init 0] [file join $out ps7_init.tcl]
set fd [open [file join $out timing.json] w]
puts $fd "{\"axi_hz\":133333333,\"serializer_hz\":200000000,\"word_hz\":100000000,\"setup_slack_ns\":$setup,\"hold_slack_ns\":$hold}"
close $fd
puts "SWD200_ROUTED setup=$setup hold=$hold"
