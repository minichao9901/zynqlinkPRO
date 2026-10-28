# Read the firmware's packet-engine counters and per-metric profiling from RAM.
# Usage: xsct tools/read_probe_counters.tcl
if {[catch {connect -url tcp:127.0.0.1:3121} err]} {
    connect
}
targets -set -filter {name =~ "APU"}
stop

proc u32 {a} { return [mrd -force -value $a] }

set taken    [u32 0x0012b9f4]
set fallback [u32 0x0012b9e8]
set req      [u32 0x0012b9e4]
set status   [u32 0x0012b9ec]
puts [format "dbg_pkt_taken=%u fallback=%u req=0x%02x status=0x%08x" $taken $fallback $req $status]

set names {EXEC05 EXEC06_READ EXEC06_WRITE PACKET_READ PACKET_WRITE DMA_UPLOAD DMA_DOWNLOAD COPY QUEUE_WAIT USB_IN USB_SUBMIT}
set base 0x0012ba20
# XTime counts at CPU/2 = 333.3 MHz on this part, so one count is ~3 ns.
for {set i 0} {$i < 11} {incr i} {
    set a [expr {$base + $i*16}]
    set lo [u32 $a]
    set hi [u32 [expr {$a+4}]]
    set ticks [expr {$lo + ($hi << 32)}]
    set calls [u32 [expr {$a+8}]]
    set bytes [u32 [expr {$a+12}]]
    set us [expr {$ticks / 333.3333}]
    puts [format "%-13s calls=%u bytes=%u ticks=%s us=%.1f" [lindex $names $i] $calls $bytes $ticks $us]
}
con
