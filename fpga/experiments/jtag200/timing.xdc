# PS-generated clocks are annotated by the block design. FCLK1 is constrained
# at its fastest runtime reference (50 MHz); FCLK0 remains 133.333 MHz.
set axi_clock [get_clocks -of_objects [get_pins -hier -filter {NAME =~ */processing_system7_0/FCLK_CLK0}]]
set word_clocks [get_clocks -include_generated_clocks -of_objects [get_pins -hier -filter {NAME =~ */processing_system7_0/FCLK_CLK1}]]
# Handshake crossings are synchronized at their endpoints. Bound physical delay.
set_max_delay -datapath_only 7.500 -from $axi_clock -to $word_clocks
set_max_delay -datapath_only 7.500 -from $word_clocks -to $axi_clock
