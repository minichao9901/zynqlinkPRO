if {[llength $argv] != 2} {error "Expected ELF and BIT paths"}
set elf [file normalize [lindex $argv 0]]
set bit [file normalize [lindex $argv 1]]
if {![file exists $elf]} {error "ELF does not exist: $elf"}
if {![file exists $bit]} {error "BIT does not exist: $bit"}

# Connect to an already running hw_server, otherwise start one.
if {[catch {connect -url tcp:127.0.0.1:3121} err]} {
    connect
}
puts [targets]
targets -set -filter {name =~ "APU"}
rst -system
after 1000

set root [file normalize [file join [file dirname [info script]] ..]]
set init [file join $root prebuilt ps7_init.tcl]
if {![file exists $init]} {
    # Fallback for the original development workspace layout.
    set init [file join $root reference legacy_zynq PS_CherryUSB_Minichao \
        PS_CherryUSB_Minichao.sdk system_wrapper_hw_platform_0 ps7_init.tcl]
}
if {![file exists $init]} {error "ps7_init.tcl not found (expected prebuilt/ps7_init.tcl)"}
source $init
ps7_init
ps7_post_config

targets -set -filter {name =~ "xc7z020"}
fpga -f $bit
after 300
targets -set -filter {name =~ "ARM*#0"}
rst -processor
configparams force-mem-access 1
set feature_value [mrd -value 0x4001004c]
puts [format "LOADED_SWD_FEATURES=0x%08X" $feature_value]
if {$feature_value & 4} {puts [format "LOADED_PACKET_SIGNATURE=0x%08X" [mrd -value 0x42020000]]}
dow -chunksize 4096 $elf
con
after 2000
puts "PC=[rrd pc]"
disconnect
exit
