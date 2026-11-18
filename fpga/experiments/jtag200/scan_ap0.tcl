# Sourced after the client selected the specific cable's physical MEM-AP0.
proc read_word {address} {
    return [lindex [physrd -force -value $address] 0]
}
proc wait_mask {address mask expected} {
    for {set attempt 0} {$attempt < 200} {incr attempt} {
        if {([read_word $address] & $mask) == $expected} {return}
        after 1
    }
    error [format "Timed out at 0x%08x waiting for mask 0x%x == 0x%x" $address $mask $expected]
}
proc profile {index taps hz half} {
    if {[read_word 0x2ff00] != 0x4a323030 || [read_word 0x40000000] != 0x4a323030} {
        error "Expected the running experimental J200 bit/ELF pair"
    }
    set request [expr {([read_word 0x2ff10] + 1) & 0xffffffff}]
    physwr -force 0x2ff08 $index
    physwr -force 0x2ff0c $taps
    physwr -force 0x2ff04 $request
    wait_mask 0x2ff10 0xffffffff $request
    set rc [read_word 0x2ff14]
    if {$rc != 0 || [read_word 0x2ff1c] != $hz || [read_word 0x2ff20] != $half} {
        error "JTAG200 profile failed (error $rc)"
    }
    puts [format "JTAG200_FCLK1_CTRL=%08x nominal_tck=%d taps=%d slots=%d" [read_word 0xf8000180] $hz $taps $half]
}
proc scan_jtag {tx rx len} {
    wait_mask 0x40000004 0x1f 0x05
    physwr -force -bin -file $tx 0x40001000 $len
    physwr -force 0x40000008 [expr {1 | (($len - 1) << 8)}]
    wait_mask 0x40000004 0x1f 0x0f
    set rc [catch {physrd -force -bin -file $rx 0x40002000 $len} result]
    physwr -force 0x40000008 0
    wait_mask 0x40000004 0x1f 0x05
    if {$rc} {error $result}
}
