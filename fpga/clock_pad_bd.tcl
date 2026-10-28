# BD port DIR is read-only in Vivado 2018.3; preserve its net and recreate it.
set clock_port [get_bd_ports -quiet swclk_0]
if {[llength $clock_port] && [get_property DIR $clock_port] ne "IO"} {
    delete_bd_objs $clock_port
    create_bd_port -dir IO swclk_0
}
set clock_port [get_bd_ports swclk_0]
# Recreate the net after the module's OUT -> IO upgrade. Reusing its old
# net leaves a stale source classification in Vivado 2018.3: the BD can
# look connected while generated system.v omits the .swclk connection.
set clock_nets [lsort -unique [concat \
    [get_bd_nets -quiet -of_objects $clock_port] \
    [get_bd_nets -quiet -of_objects [get_bd_pins swd_controller_0/swclk]]]]
if {[llength $clock_nets]} {delete_bd_objs $clock_nets}
connect_bd_net $clock_port [get_bd_pins swd_controller_0/swclk]
