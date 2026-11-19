# Source after board.tcl. 'saved' holds a verified 4 KiB F103 backup.
proc f103_word {addr} {
    return [lindex [swd_require [list 5 $addr 15 0 14 0]] 2]
}
proc f103_low {} {
    swd_config 0 0 20 20 8
    swd_require {16 0}
    if {[lindex [swd_require {2 0}] 0] != 0x1ba01477} {error "F103 DP identity"}
    swd_require {0 0x1e 4 0x50000000 8 0 1 0x23000052}
    if {[f103_word 0xe0042000]!=0x10036414 || [f103_word 0xe000ed00]!=0x411fc231 ||
        ([f103_word 0x1ffff7e0]&65535)!=512} {error "F103 target identity"}
}
proc f103_page {addr} {
    set batch [list 5 $addr]
    for {set i 0} {$i<256} {incr i} {lappend batch 15 0}
    lappend batch 14 0
    return [lrange [swd_require $batch] 2 end]
}
proc f103_check {repair} {
    global saved guards
    f103_low
    if {[f103_word 0x20007ffc]!=[lindex $guards 0] || [f103_word 0x20009000]!=[lindex $guards 1]} {
        error "F103 guard mismatch"
    }
    for {set page 3} {$page>=0} {incr page -1} {
        set addr [expr {0x20008000+1024*$page}]
        set expected [lrange $saved [expr {$page*256}] [expr {$page*256+255}]]
        if {[f103_page $addr] ne $expected} {
            if {!$repair || $page!=0} {error "F103 backup mismatch at page $page"}
            if {[lindex [swd_require [list 5 $addr 7 0 14 0]] 2]!=$addr} {error "restore TAR"}
            set c {}
            foreach v $expected {lappend c 13 $v}
            lappend c 14 0
            swd_require $c
            if {[f103_page $addr] ne $expected} {error "F103 recovery readback mismatch"}
            puts "RECOVERED page=$page"
        }
    }
}
proc f103_window {rate tap ack data idle mode rounds} {
    f103_low
    set profile [swd_config $rate $tap $ack $data $idle]
    swd_wait 0x2ff40 0xffffffff 0x4631424d
    set seq [expr {([swd_rd 0x2ff44]+1)&0xffffffff}]
    swd_wr 0x2ff4c $mode
    swd_wr 0x2ff50 $rounds
    swd_wr 0x2ff44 $seq
    set deadline [expr {[clock milliseconds]+120000}]
    while {[swd_rd 0x2ff48]!=$seq} {
        if {[clock milliseconds]>$deadline} {error "F103 batch deadline"}
        after 5
    }
    set result [physrd -force -value 0x2ff40 27]
    puts "WINDOW $rate $tap $ack $data $idle $mode $rounds $profile $result"
    return [expr {[lindex $result 5]==0 && [lindex $result 6]==$rounds &&
                  [lindex $result 7]==$mode*$rounds}]
}
