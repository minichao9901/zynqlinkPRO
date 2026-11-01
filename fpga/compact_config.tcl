# Diagnostics are a build-time choice; protocol/register apertures stay intact.
source [file join [file dirname [info script]] rtl_debug_profile.tcl]
set want_diagnostics [zynqlink_rtl_debug_mode $argv]
set ::zynqlink_rtl_debug $want_diagnostics
puts "RTL_BUILD_MODE=[expr {$want_diagnostics ? {debug} : {release}}] RTL_DEBUG=$want_diagnostics"
set swd [get_bd_cells swd_controller_0]
set diagnostic_config_changed [expr {[get_property CONFIG.ENABLE_DIAGNOSTICS $swd] != $want_diagnostics}]
if {$diagnostic_config_changed} {
    set_property CONFIG.ENABLE_DIAGNOSTICS $want_diagnostics $swd
    save_bd_design
}
puts "SWD_JTAG_DIAGNOSTICS=$want_diagnostics"
