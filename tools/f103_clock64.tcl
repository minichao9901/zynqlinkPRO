# Volatile test configuration: HSI/2 x16 = 64 MHz, independent of board HSE.
# Call after reset halt. No flash contents or option bytes are changed.
mww 0x40022000 0x32
mww 0x40021004 0x00380400
mmw 0x40021000 0x01000000 0
set ready 0
for {set n 0} {$n < 100} {incr n} {
    if {([lindex [read_memory 0x40021000 32 1] 0] & 0x02000000) != 0} {set ready 1; break}
    sleep 1
}
if {!$ready} {error "F103 PLL did not lock"}
mmw 0x40021004 2 3
set cfgr [lindex [read_memory 0x40021004 32 1] 0]
if {($cfgr & 0xC) != 8} {error "F103 failed to select PLL: $cfgr"}
echo "F103 HCLK=64MHz HSI/2x16 CFGR=$cfgr"
