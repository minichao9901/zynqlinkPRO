# These two queues transfer ownership with synchronized request/completion flags.
# AXI freezes configuration and TX RAM before START. AXI reads status only after
# DONE crosses back, and the worker holds the results until the next request.
# Bound the physical crossing to one fastest AXI cycle. Do not relax the pad,
# compatibility, clock gearbox, trace receiver, or either intra-domain path.
set quad_dma [expr {[info exists ::env(ZYNQLINK_QUAD_DMA)] && $::env(ZYNQLINK_QUAD_DMA)}]
if {!$quad_dma} {
foreach {engine divided} {sio_jtag octet_raw sio_swd quad_raw sio_aux quad_raw} {
    if {($sio_slice==1 && $engine eq "sio_swd") || ($sio_slice==2 && $engine eq "sio_jtag")} {continue}
    set fast_regs [filter [all_registers -clock [get_clocks clk_fpga_0]] "NAME =~ */$engine/inst/* && REF_NAME =~ FD*"]
    set link_regs [filter [all_registers -clock [get_clocks $divided]] "NAME =~ */$engine/inst/* && REF_NAME =~ FD*"]
    if {![llength $fast_regs] || ![llength $link_regs]} {error "Missing queue domains for $engine"}
    set_max_delay -datapath_only 7.500 -from [get_clocks clk_fpga_0] -to $link_regs
    set_max_delay -datapath_only 7.500 -from [get_clocks $divided] -to $fast_regs
}
} else {
    # The JTAG octet clock and the GP1 quad clock are related MMCM outputs.
    # These queue and payload paths use normal generated-clock timing.
    set config_meta [get_cells -hier -filter {NAME =~ *g_quad_config.config_meta_reg* && ASYNC_REG == TRUE}]
    if {![llength $config_meta]} {error "Missing AXI-to-host live-profile synchronizers"}
    set_max_delay -datapath_only 7.500 -from [get_clocks quad_raw] -to $config_meta
}

# Only the first synchronizer stage samples an asynchronous compatibility
# level. Keep the second stage and all high-speed protocol paths timed.
set meta [get_cells -hier -filter {NAME =~ *g_selectio*legacy_meta_reg* && REF_NAME =~ FD*}]
if {($sio_slice==0 && [llength $meta]!=5) || ![llength $meta]} {error "Missing five compatibility input synchronizers"}
set_max_delay -datapath_only 7.500 -from [get_clocks clk_fpga_0] -to $meta

# Live DAP descriptors remain stable until the corresponding completion toggle.
# These constraints apply only to the two handoff engines, not the serializer.
foreach {link divided} {swd_link quad_raw jtag_link octet_raw} {
    if {($sio_slice==1 && $link eq "swd_link") || ($sio_slice==2 && $link eq "jtag_link")} {continue}
    set io_regs [filter [all_registers -clock [get_clocks $divided]] "NAME =~ *g_live_link*$link/* && REF_NAME =~ FD*"]
    set host_regs [filter [all_registers -clock [get_clocks clk_fpga_0]] "NAME =~ *g_live_link*$link/crossing/* && REF_NAME =~ FD*"]
    if {![llength $io_regs] || ![llength $host_regs]} {error "Missing live $link crossing"}
    set_max_delay -datapath_only 7.500 -from [get_clocks clk_fpga_0] -to $io_regs
    set_max_delay -datapath_only 7.500 -from [get_clocks $divided] -to $host_regs
}
