# Same placed/routed logic; change only SWCLK pad properties for electrical A/B.
if {[llength $argv] != 3} {error "Expected OUTPUT_BIT SLEW DRIVE"}
set output [file normalize [lindex $argv 0]]
set slew [lindex $argv 1]
set drive [lindex $argv 2]
if {$slew ni {FAST SLOW} || $drive ni {4 8}} {error "Use FAST/SLOW and 4/8 mA"}
set root [file normalize [file join [file dirname [info script]] ..]]
open_checkpoint [file join $root build fpga_dma_global system_wrapper_verified.dcp]
set_property SLEW $slew [get_ports swclk_0]
set_property DRIVE $drive [get_ports swclk_0]
set setup [get_property SLACK [get_timing_paths -max_paths 1 -delay_type max]]
set hold [get_property SLACK [get_timing_paths -max_paths 1 -delay_type min]]
if {$setup < 0 || $hold < 0} {error "IO variant timing failed: setup=$setup hold=$hold"}
report_io -file ${output}.io.rpt
write_bitstream -force $output
puts "IO_VARIANT_READY bit=$output slew=$slew drive=$drive setup=$setup hold=$hold"
