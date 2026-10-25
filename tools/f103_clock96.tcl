# Volatile STM32F103 overclock experiment: external HSE x12 = 96 MHz.
# No flash/option-byte writes. Fails if the board has no usable HSE.
mww 0x40022000 0x32
mmw 0x40021000 0x00010000 0
set ready 0
for {set n 0} {$n < 100} {incr n} {
    if {([lindex [read_memory 0x40021000 32 1] 0] & 0x00020000) != 0} {set ready 1; break}
    sleep 1
}
if {!$ready} {error "F103 HSE did not lock"}
mmw 0x40021000 0x01000000 0
mww 0x40021004 0x00290400
mmw 0x40021000 0x01000000 0
set ready 0
for {set n 0} {$n < 100} {incr n} {
    if {([lindex [read_memory 0x40021000 32 1] 0] & 0x02000000) != 0} {set ready 1; break}
    sleep 1
}
if {!$ready} {error "F103 96 MHz PLL did not lock"}
mmw 0x40021004 2 3
set cfgr [lindex [read_memory 0x40021004 32 1] 0]
if {($cfgr & 0xC) != 8} {error "F103 failed to select 96 MHz PLL: $cfgr"}
echo "F103 HCLK=96MHz HSEx12 CFGR=$cfgr"
