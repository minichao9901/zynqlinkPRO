# Reuse a linked, unplaced RAW4+DDR checkpoint and change only the J7 pinout.
set root [file normalize [file join [file dirname [info script]] ..]]
if {[llength $argv] != 1 || ![info exists ::env(ZYNQLINK_FPGA_OUT)]} {
    error "Provide the RAW4+DDR post-opt DCP and a new ZYNQLINK_FPGA_OUT directory"
}
set checkpoint [file normalize [lindex $argv 0]]
set out [file normalize $::env(ZYNQLINK_FPGA_OUT)]
if {![file isfile $checkpoint] || [file exists $out]} {
    error "Checkpoint missing or output directory already exists"
}
if {[info exists ::env(ZYNQLINK_IMPLEMENT_FCLK_HZ)] && $::env(ZYNQLINK_IMPLEMENT_FCLK_HZ) ne "133333333"} {
    error "The adapter uses the 133.333333MHz implementation constraint"
}
set ::env(ZYNQLINK_RAW_TRACE) 4
set ::env(ZYNQLINK_ETM_DDR) 1
set ::env(ZYNQLINK_IMPLEMENT_FCLK_HZ) 133333333
file mkdir $out
source [file join $root fpga run_threads.tcl]
open_checkpoint $checkpoint
if {[get_property PART [current_design]] ne "xc7z020clg400-2" ||
    [llength [get_cells -quiet -hier -filter {REF_NAME =~ LUT* && IS_PLACED}]] ||
    [llength [get_cells -quiet -hier -filter {NAME =~ *raw_oversample*pad_meta_reg*}]] != 5 ||
    ![llength [get_cells -quiet -hier -filter {NAME =~ *etm_ddr_0*}]]} {
    error "Expected the linked, unplaced XC7Z020 RAW4+DDR design"
}
foreach {name original_ball} {
    swclk_0 D20 swdio_0 D19
    {gpio_rtl_0_tri_io[0]} B19 {gpio_rtl_0_tri_io[1]} A20
    {gpio_rtl_0_tri_io[2]} E19 {gpio_rtl_0_tri_io[3]} E18
    trace_clk H16 {trace_data[0]} H15 {trace_data[1]} G15 {trace_data[2]} H17 {trace_data[3]} N15
} {
    set port [get_ports $name]
    if {[get_property PACKAGE_PIN $port] ne $original_ball} {error "Unexpected original pin for $name"}
    reset_property PACKAGE_PIN $port
}
# Reserve the RTCK pad as an input with no connection to the JTAG clock engine.
create_port -direction IN rtck
create_cell -reference IBUF j7_rtck_input
create_net j7_rtck_pad
connect_net -net j7_rtck_pad -objects [list [get_ports rtck] [get_pins j7_rtck_input/I]]
set_property DONT_TOUCH true [get_cells j7_rtck_input]
read_xdc [file join $root fpga constraints j7_adapter_pins.xdc]
source [file join $root fpga probe_io_timing.tcl]
place_design -directive Explore
phys_opt_design -directive Explore
route_design -directive Explore
report_io -file [file join $out j7_adapter_io.rpt]
report_route_status -file [file join $out route_status.rpt]
set ::zynqlink_verify_checkpoint [file join $out j7_adapter_routed.dcp]
write_checkpoint $::zynqlink_verify_checkpoint
close_design
set argv {}
source [file join $root fpga verify_routed.tcl]
