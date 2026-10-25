# Usage: run_xsct.py download_cdc.tcl <cdc_bench.elf>
# RAM download only. This does not program QSPI or an SD card.
if {[llength $argv] != 1} {error "Expected exactly one ELF path"}
set elf [file normalize [lindex $argv 0]]
if {![file exists $elf]} {error "ELF does not exist: $elf"}
connect -url tcp:127.0.0.1:3121
puts [targets]
targets -set -filter {name =~ "APU"}
rst -system
after 1000
set root [file normalize [file join [file dirname [info script]] ..]]
set init [file join $root reference legacy_zynq PS_CherryUSB_Minichao PS_CherryUSB_Minichao.sdk system_wrapper_hw_platform_0 ps7_init.tcl]
if {![file exists $init]} {error "Board initialization script missing: $init"}
source $init
ps7_init
ps7_post_config
targets -set -filter {name =~ "ARM*#0"}
rst -processor
dow -chunksize 4096 $elf
con
after 1500
puts "USB USBCMD / USBSTS / PORTSC1:"
puts [mrd 0xE0002140 2]
puts [mrd 0xE0002184 1]
disconnect
exit
