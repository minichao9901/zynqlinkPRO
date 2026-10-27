# Report where the SWJ output registers landed and their clock-to-out path.
open_checkpoint [file join [pwd] build fpga_dma_global system_wrapper_verified.dcp]
foreach name {tck_reg tms_reg tdi_reg} {
    set cells [get_cells -hier -quiet -filter "NAME =~ *$name"]
    foreach c $cells {
        puts [format "%-40s site=%s type=%s" $c [get_property SITE $c] [get_property PRIMITIVE_TYPE $c]]
    }
}
puts "--- clock-to-out paths from those registers ---"
set paths [get_timing_paths -max_paths 6 -to [get_cells -hier -quiet -filter {NAME =~ *tck_reg*}]]
foreach p $paths {
    puts [format "slack=%s delay=%s" [get_property SLACK $p] [get_property REQUIREMENT $p]]
}
puts "--- pin sites for the SWJ ports ---"
foreach port {swclk swdio nreset} {
    set pins [get_ports -quiet $port]
    foreach p $pins {
        puts [format "%-10s %s" $port [get_property SITE_OF $p]]
    }
}
