# Runtime FCLK changes independently of the pad clocks. These are the first
# stages of two-flop AXI-to-pad ownership synchronizers; bound interconnect delay.
set sio_ownership_meta [get_cells -hier -filter {ASYNC_REG == TRUE && (NAME =~ */sio_clock/inst/meta_reg* || NAME =~ *g_live_select.live_jtag_sync_reg?0? || NAME =~ *g_live_select.live_swd_sync_reg?0? || NAME =~ *legacy_jtag_sync_reg?0?)}]
if {($sio_slice==0 && [llength $sio_ownership_meta]<5) || ![llength $sio_ownership_meta]} {error "Missing SelectIO ownership synchronizers"}
set_max_delay -datapath_only 7.500 -from [get_clocks clk_fpga_0] -to $sio_ownership_meta
