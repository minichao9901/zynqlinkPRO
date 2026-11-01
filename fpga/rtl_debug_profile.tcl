# Optional observation instrumentation only; SWD/JTAG/RTT/HSS business logic
# is never disabled by this switch. Keep the legacy --diagnostics alias.
proc zynqlink_rtl_debug_mode {arguments} {
    set legacy [expr {[lsearch -exact $arguments --diagnostics] >= 0}]
    if {[info exists ::env(ZYNQLINK_RTL_DEBUG)]} {
        set value $::env(ZYNQLINK_RTL_DEBUG)
        if {$value ni {0 1}} {error "ZYNQLINK_RTL_DEBUG must be exactly 0 or 1"}
        if {$legacy && $value==0} {error "--diagnostics conflicts with explicit release ZYNQLINK_RTL_DEBUG=0"}
        return $value
    }
    return $legacy
}
