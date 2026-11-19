# Sourced inside the cable-bound physical MEM-AP0 session.
proc swd_rd {address} { return [physrd -force -value $address] }
proc swd_wr {address value} { physwr -force $address $value }

proc swd_wait {address mask expected} {
    for {set tries 0} {$tries < 250} {incr tries} {
        set value [swd_rd $address]
        if {($value & $mask) == $expected} { return $value }
        after 1
    }
    error [format "timed out at 0x%08x, last 0x%08x" $address $value]
}

proc swd_config {index tap ack data idle} {
    swd_wait 0x2ff00 0xffffffff 0x53323030
    swd_wait 0x40000004 32 32
    if {[info exists ::board_guard]} {
        swd_wr 0x4000001c [expr {$index==0 ? 0 : ($::board_guard<<4)}]
    }
    if {[swd_rd 0x2ff08]==$index && [swd_rd 0x2ff18]==0 &&
        [swd_rd 0x2ff04]==[swd_rd 0x2ff14]} {
        set rate [expr {[swd_rd 0x4000000c]&3}]
        swd_wr 0x4000000c [expr {($idle<<14)|($data<<8)|($ack<<2)|$rate}]
        swd_wr 0x40000018 $tap
        if {[swd_rd 0x40000018]!=$tap} {error "tap mismatch"}
        return [list [swd_rd 0x2ff20] [swd_rd 0xf8000180] [swd_rd 0xf8000108] [swd_rd 0x4000000c]]
    }
    set request [expr {([swd_rd 0x2ff04] + 1) & 0xffffffff}]
    swd_wr 0x2ff08 $index
    swd_wr 0x2ff0c [expr {($idle << 14) | ($data << 8) | ($ack << 2)}]
    swd_wr 0x2ff10 $tap
    swd_wr 0x2ff04 $request
    swd_wait 0x2ff14 0xffffffff $request
    if {[swd_rd 0x2ff18]} { error "swd200 clock mailbox failed" }
    swd_wait 0x40000004 33 33
    if {[swd_rd 0x40000018] != $tap} { error "tap readback mismatch" }
    return [list [swd_rd 0x2ff20] [swd_rd 0xf8000180] [swd_rd 0xf8000108] [swd_rd 0x4000000c]]
}

proc swd_batch {commands} {
    set count [expr {[llength $commands] / 2}]
    if {$count < 1 || $count > 512 || [llength $commands] % 2} { error "bad command count" }
    swd_wait 0x40000004 33 33
    physwr -force 0x40001000 $commands
    swd_wr 0x40000010 $count
    swd_wait 0x40000004 37 37
    set summary [swd_rd 0x40000014]
    set actual [expr {$summary & 0x3ff}]
    set values {}
    if {$actual} { set values [physrd -force -value 0x40002000 $actual] }
    return [linsert $values 0 $summary]
}

proc swd_require {commands} {
    set result [swd_batch $commands]
    if {([lindex $result 0] & 0xffff) != [llength $commands] / 2} { error "SWD batch: $result" }
    return [lrange $result 1 end]
}
