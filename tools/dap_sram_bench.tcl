set base 0x20000000
set size 0x5000
set pat results/daplink/sram/pat_20480.bin
set outdir results/daplink/sram

init
halt
load_image $pat $base
echo "PATTERN_LOADED"

foreach s {1000 5000 10000 20000 30000 50000} {
    if {[catch {adapter speed $s} e]} {
        echo "SPEED $s SETUP_ERR $e"
        continue
    }
    catch {dump_image $outdir/warm_$s.bin $base $size}
    for {set i 0} {$i < 2} {incr i} {
        if {[catch {
            set t0 [clock milliseconds]
            dump_image $outdir/dump_${s}_$i.bin $base $size
            set t1 [clock milliseconds]
        } e]} {
            echo "SPEED $s READ_$i FAIL $e"
            continue
        }
        echo "READ speed=$s run=$i ms=[expr {$t1-$t0}]"
    }
    for {set i 0} {$i < 2} {incr i} {
        if {[catch {
            set t2 [clock milliseconds]
            load_image $pat $base
            set t3 [clock milliseconds]
        } e]} {
            echo "SPEED $s WRITE_$i FAIL $e"
            continue
        }
        echo "WRITE speed=$s run=$i ms=[expr {$t3-$t2}]"
    }
}
exit
