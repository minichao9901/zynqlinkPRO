# Configuration cannot change between GO and synchronized DONE. Count and bank
# are valid before a worker accesses its RAM port. Keep the bound on these
# immutable descriptor bits, including the RAM pins outside the queue hierarchy.
if {[info exists ::env(ZYNQLINK_QUAD_DMA)] && $::env(ZYNQLINK_QUAD_DMA)} {return}
foreach engine {jtag swd} {
    if {($sio_slice==1 && $engine eq "swd") || ($sio_slice==2 && $engine eq "jtag")} {continue}
    set held [get_cells -hier -filter "NAME =~ */sio_${engine}/inst/* && REF_NAME =~ FD* && (NAME =~ */payload_config_reg* || NAME =~ */block_count_reg* || NAME =~ */block_write_reg* || NAME =~ */count_reg*)"]
    set ram [get_cells -hier -filter "NAME =~ */sio_payload/inst/${engine}/* && REF_NAME =~ RAMB*"]
    if {![llength $held] || [llength $ram]!=2} {error "Payload bank/descriptor crossing missing for $engine"}
    set_max_delay -datapath_only 7.500 -from $held -to $ram
}
