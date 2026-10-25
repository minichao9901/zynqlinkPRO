connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "GPIO before=[mrd 0x40000000 1]"
for {set i 0} {$i < 60} {incr i} {
    mwr 0x40000000 0x4
    after 8
    mwr 0x40000000 0x7
    after 8
}
puts "GPIO after=[mrd 0x40000000 1]"
disconnect
exit
