# The command/result BRAMs and the synchronized request/completion flags
# establish ownership. Descriptor and summary bits are held stable before
# and during their receiving handshakes. Bound crossing delays to one FCLK0.
set axi_clock [get_clocks -of_objects [get_pins -hier -filter {NAME =~ */processing_system7_0/FCLK_CLK0}]]
set word_clock [get_clocks word_raw]
if {[llength $axi_clock] != 1 || [llength $word_clock] != 1} {
    error "SWD200 AXI/CLKDIV constraints could not be resolved"
}
set_max_delay -datapath_only 7.500 -from $axi_clock -to $word_clock
set_max_delay -datapath_only 7.500 -from $word_clock -to $axi_clock
