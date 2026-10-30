# Diagnostics are a build-time choice; protocol/register apertures stay intact.
set want_diagnostics [expr {[lsearch -exact $argv --diagnostics] >= 0}]
set swd [get_bd_cells swd_controller_0]
set diagnostic_config_changed [expr {[get_property CONFIG.ENABLE_DIAGNOSTICS $swd] != $want_diagnostics}]
if {$diagnostic_config_changed} {
    set_property CONFIG.ENABLE_DIAGNOSTICS $want_diagnostics $swd
    save_bd_design
}
puts "SWD_JTAG_DIAGNOSTICS=$want_diagnostics"
