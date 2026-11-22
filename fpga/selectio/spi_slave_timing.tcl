# L15 is SWCLK when driven by the probe and external SCK in SPI slave
# mode. The SPI slave oversamples it against the independent MMCM. Cut
# only the external pad-to-first-sampler path, not the SWCLK output or
# the registered paths from the ISERDES into the decoder.
set spi_clock_rx [get_cells -quiet -hier -filter {REF_NAME == ISERDESE2 && NAME =~ */clock_rx/shift}]
if {[llength $spi_clock_rx]} {
    set spi_async_input [get_pins -of_objects $spi_clock_rx -filter {REF_PIN_NAME == DDLY}]
    if {[llength $spi_async_input] != 1} {error "Ambiguous SPI slave SCK sampler"}
    set_false_path -from [get_ports swclk_0] -to $spi_async_input
    puts "SELECTIO_SPI_EXTERNAL_SCK_ASYNC $spi_async_input"
}
