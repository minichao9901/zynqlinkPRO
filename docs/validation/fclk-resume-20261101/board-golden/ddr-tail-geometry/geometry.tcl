connect -url tcp:127.0.0.1:3121
targets -set -filter {name =~ "APU"}
set addresses {0x19c00000 0x39c00000 0x1ffffff0 0x3ffffff0}
set backup [dict create]
# Gather all backups before the first write. No CPU reset, stop or continue.
foreach a $addresses {
  set words [mrd -address-space AP0 -force -value $a 4]
  if {[llength $words]!=4} {error "Incomplete backup"}
  dict set backup $a $words
  puts "DDR_BACKUP $a $words"
}
set rc [catch {
  puts DDR_WRITE_BEGIN
  set i 0
  foreach a $addresses {
    for {set j 0} {$j<4} {incr j} {
      mwr -address-space AP0 -bypass-cache-sync -force [expr {$a+4*$j}] [expr {0xa5190000 | ($i<<8) | $j}]
    }
    incr i
  }
  foreach a $addresses {puts "DDR_PATTERN $a [mrd -address-space AP0 -force -value $a 4]"}
} why]
# Every sampled location is restored even when a write/read raised an error.
# Aliased backups are equal because they were all collected before mutation.
set restore_errors {}
foreach a [lreverse $addresses] {
  set j 0
  foreach word [dict get $backup $a] {
    if {[catch {mwr -address-space AP0 -bypass-cache-sync -force [expr {$a+4*$j}] $word} msg]} {lappend restore_errors $msg}
    incr j
  }
}
foreach a $addresses {
  set restored [mrd -address-space AP0 -force -value $a 4]
  puts "DDR_RESTORED $a $restored"
  if {$restored ne [dict get $backup $a]} {lappend restore_errors "Restore mismatch at $a"}
}
disconnect
if {[llength $restore_errors]} {error $restore_errors}
if {$rc} {error $why}
puts DDR_RESTORE_VERIFIED
exit
