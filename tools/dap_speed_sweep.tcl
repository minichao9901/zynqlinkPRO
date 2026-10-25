set base 0x20000000
set size 0x5000
set pat results/daplink/sram/pat_20480.bin

init
reset halt
load_image $pat $base
echo "PATTERN_LOADED"

foreach s {1000 2000 5000 10000 15000 20000 30000 50000} {
    if {[catch {adapter speed $s} e]} {
        echo "SPEED $s SETUP_ERR $e"
        continue
    }
    catch {dump_image results/daplink/sram/sw_warm.bin $base $size}
    set ok 1
    if {[catch {
        set t0 [clock milliseconds]
        for {set i 0} {$i < 10} {incr i} {
            dump_image results/daplink/sram/sw_read_$s.bin $base $size
        }
        set t1 [clock milliseconds]
        set t2 [clock milliseconds]
        for {set i 0} {$i < 10} {incr i} {
            load_image $pat $base
        }
        set t3 [clock milliseconds]
    } e]} {
        echo "SPEED $s FAIL $e"
        set ok 0
    }
    if {$ok} {
        echo "RESULT speed=$s read_ms=[expr {$t1-$t0}] write_ms=[expr {$t3-$t2}]"
    }
}
exit
