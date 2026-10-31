# hsi.bat generate_bsp.tcl <output-directory>
if {[llength $argv] != 1} {error "Expected BSP output directory"}
open_hw_design [file join [file dirname [info script]] system.hdf]
create_sw_design qspi_boot_bsp -proc ps7_cortexa9_0 -os standalone
generate_bsp -dir [lindex $argv 0]
exit
