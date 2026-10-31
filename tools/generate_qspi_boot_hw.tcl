# Export matching QSPI-enabled PS initialization from a future combined project.
# Run in Vivado: -source tools/generate_qspi_boot_hw.tcl -tclargs PROJECT.xpr OUTPUT_DIR
# This file is not invoked by merge or by regression scripts.
if {[llength $argv] != 2} {error "Expected PROJECT.xpr and OUTPUT_DIR"}
set project [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {![file isfile $project]} {error "Project does not exist: $project"}
open_project $project
set bd [get_files -quiet */system.bd]
if {[llength $bd] != 1} {error "Expected exactly one system.bd"}
open_bd_design $bd
set ps [get_bd_cells processing_system7_0]
# Keep MIO8 available for USB PHY reset. Preserve all unrelated PS/ETM settings.
set_property -dict [list CONFIG.PCW_QSPI_PERIPHERAL_ENABLE {1} \
    CONFIG.PCW_QSPI_QSPI_IO {MIO 1 .. 6} \
    CONFIG.PCW_QSPI_GRP_SINGLE_SS_ENABLE {1} \
    CONFIG.PCW_QSPI_GRP_FBCLK_ENABLE {0} \
    CONFIG.PCW_QSPI_PERIPHERAL_FREQMHZ {200}] $ps
validate_bd_design
save_bd_design
generate_target all $bd
file mkdir $output
write_hwdef -force -file [file join $output system.hdf]
set directory [file join [file dirname [lindex $bd 0]] ip system_processing_system7_0_0]
foreach name {ps7_init.c ps7_init.h ps7_init.tcl} {
    set input [file join $directory $name]
    if {![file isfile $input]} {error "Missing generated initialization: $input"}
    if {[file normalize $input] ne [file normalize [file join $output $name]]} {
        file copy -force $input [file join $output $name]
    }
}
puts "QSPI_BOOT_HW_EXPORTED $output"
close_project
