connect -url {tcp:127.0.0.1:3121}
set selected 0
for {set n 0} {$n < 50} {incr n} {
 if {![catch {targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}} why]} {set selected 1;break}
 after 100
}
if {!$selected} {error $why}
::tcf::send_command [::xsdb::getcurchan] XilinxReset reset sso{[dict create suspend b]} e [list [::xsdb::getcurtarget] system [dict create suspend 0]]
puts RESET_NO_HALT
disconnect
exit
