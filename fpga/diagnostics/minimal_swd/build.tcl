set here [file dirname [file normalize [info script]]]
set root [file normalize [file join $here ../../..]]
set out [file join $root build minimal_swd]
set config_file [file join $here ps7_config.tcl]
if {![file exists $config_file]} {
    # Read the board's existing PS/DDR setup once, then retain an explicit
    # source snapshot so subsequent builds need no production build project.
    open_project [file join $root build fpga_dma_global zynqlink_dma.xpr]
    open_bd_design [get_files system.bd]
    set ps7_config {}
    set ps [get_bd_cells processing_system7_0]
    foreach p [lsort [list_property $ps]] {
        if {[string match CONFIG.PCW_* $p]} {lappend ps7_config $p [get_property $p $ps]}
    }
    set fd [open $config_file w]
    puts $fd "# Board PS7/DDR configuration snapshot; exported with Vivado 2018.3."
    puts $fd [list set ps7_config $ps7_config]
    close $fd
    close_project
} else {source $config_file}
create_project -force minimal_swd $out -part xc7z020clg400-2
set_param general.maxThreads 8
set_property target_language Verilog [current_project]
add_files [file join $here minimal_swd_top.v]
add_files -fileset constrs_1 [file join $here pins.xdc]
set_property PROCESSING_ORDER LATE [get_files pins.xdc]
create_bd_design minimal_swd_bd
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0
set ps [get_bd_cells processing_system7_0]
set fd [open [file join $root fpga bd legacy_system.tcl] r]
set legacy_text [read $fd]
close $fd
set declared [regexp -all -inline {CONFIG\.[A-Z0-9_]+} $legacy_text]
set writable {}
foreach {p value} $ps7_config {
    if {[lsearch -exact $declared $p]>=0} {lappend writable $p $value}
}
set_property -dict $writable $ps
set_property -dict [list CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ 100 CONFIG.PCW_USE_M_AXI_GP0 1 \
 CONFIG.PCW_USE_M_AXI_GP1 0 CONFIG.PCW_USE_S_AXI_HP0 0 CONFIG.PCW_USE_S_AXI_HP1 0 \
 CONFIG.PCW_USE_S_AXI_HP2 0 CONFIG.PCW_USE_S_AXI_HP3 0 CONFIG.PCW_USE_S_AXI_ACP 0 \
 CONFIG.PCW_USE_S_AXI_GP0 0 CONFIG.PCW_USE_S_AXI_GP1 0] $ps
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 DDR
create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 FIXED_IO
foreach interface {DDR FIXED_IO} {
 connect_bd_intf_net [get_bd_intf_ports $interface] [get_bd_intf_pins processing_system7_0/$interface]
}
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 gpio
set_property -dict [list CONFIG.C_IS_DUAL 1 CONFIG.C_GPIO_WIDTH 4 CONFIG.C_ALL_OUTPUTS 1 \
 CONFIG.C_GPIO2_WIDTH 2 CONFIG.C_ALL_INPUTS_2 1] [get_bd_cells gpio]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_bus
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1] [get_bd_cells axi_bus]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset
set_property CONFIG.C_EXT_RESET_HIGH 0 [get_bd_cells reset]
foreach {name value} {one 1 zero 0} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 $name
 set_property CONFIG.CONST_VAL $value [get_bd_cells $name]
}
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_bus/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_bus/M00_AXI] [get_bd_intf_pins gpio/S_AXI]
set clock [get_bd_pins processing_system7_0/FCLK_CLK0]
foreach pin {processing_system7_0/M_AXI_GP0_ACLK gpio/s_axi_aclk axi_bus/ACLK axi_bus/S00_ACLK axi_bus/M00_ACLK reset/slowest_sync_clk} {
 connect_bd_net $clock [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins reset/ext_reset_in]
# proc_sys_reset defaults C_AUX_RESET_HIGH=0: tie auxiliary reset HIGH.
connect_bd_net [get_bd_pins one/dout] [get_bd_pins reset/dcm_locked] [get_bd_pins reset/aux_reset_in]
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins reset/mb_debug_sys_rst]
foreach pin {axi_bus/ARESETN axi_bus/S00_ARESETN axi_bus/M00_ARESETN} {
 connect_bd_net [get_bd_pins reset/interconnect_aresetn] [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins reset/peripheral_aresetn] [get_bd_pins gpio/s_axi_aresetn]
create_bd_port -dir O -from 3 -to 0 control
create_bd_port -dir I -from 1 -to 0 sense
create_bd_port -dir O -type clk fabric_clk
connect_bd_net $clock [get_bd_ports fabric_clk]
connect_bd_net [get_bd_ports control] [get_bd_pins gpio/gpio_io_o]
connect_bd_net [get_bd_ports sense] [get_bd_pins gpio/gpio2_io_i]
assign_bd_address
set_property offset 0x40000000 [get_bd_addr_segs processing_system7_0/Data/SEG_gpio_Reg]
set_property range 64K [get_bd_addr_segs processing_system7_0/Data/SEG_gpio_Reg]
validate_bd_design
save_bd_design
generate_target all [get_files minimal_swd_bd.bd]
set_property top minimal_swd_top [current_fileset]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {error "Minimal synthesis failed"}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {error "Minimal implementation failed"}
open_run impl_1
set setup [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]
set hold [get_property SLACK [get_timing_paths -max_paths 1 -delay_type min]]
report_timing_summary -report_unconstrained -file [file join $out timing.rpt]
report_io -file [file join $out io.rpt]
if {$setup < 0 || $hold < 0} {error "Minimal routed timing failed $setup $hold"}
file copy -force [file join $out minimal_swd.runs impl_1 minimal_swd_top.bit] [file join $out minimal_swd.bit]
set fd [open [file join $out timing.json] w]
puts $fd "{\"FCLK_Hz\":100000000,\"setup_slack_ns\":$setup,\"hold_slack_ns\":$hold}"
close $fd
puts "MINIMAL_SWD_READY setup=$setup hold=$hold"
