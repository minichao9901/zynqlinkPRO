# L15 is SWCLK when driven by the probe and external SCK in SPI slave
# mode. The SPI slave oversamples it against the independent MMCM. Cut
# only the external pad-to-first-sampler path, not the SWCLK output or
# the registered paths from the ISERDES into the decoder.
set spi_clock_rx [get_cells -quiet -hier -filter {REF_NAME == ISERDESE2 && NAME =~ *clock_rx/shift}]
if {[info exists ::env(ZYNQLINK_SPI_PAD_FILTER)] && $::env(ZYNQLINK_SPI_PAD_FILTER)} {
    if {[llength $spi_clock_rx] != 1} {error "Missing filtered SPI slave SCK sampler"}
    set spi_sample_clock [get_pins -of_objects $spi_clock_rx -filter {REF_PIN_NAME == CLK}]
    if {"rx_raw" ni [get_clocks -of_objects $spi_sample_clock]} {
        error "Filtered SPI slave SCK sampler is not on the 400 MHz DDR clock"
    }
}
if {[llength $spi_clock_rx]} {
    set spi_async_input [get_pins -of_objects $spi_clock_rx -filter {REF_PIN_NAME == DDLY}]
    if {[llength $spi_async_input] != 1} {error "Ambiguous SPI slave SCK sampler"}
    set_false_path -from [get_ports swclk_0] -to $spi_async_input
    puts "SELECTIO_SPI_EXTERNAL_SCK_ASYNC $spi_async_input"
}
