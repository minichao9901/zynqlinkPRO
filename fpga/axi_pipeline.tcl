# Keep the DMA/BRAM path native 32-bit; only HP0 needs a 64-bit converter.
# Register both outer boundaries to break READY chains between interconnects.
set axi_pipeline_changed 0
set no_pipeline [expr {[info exists ::zynqlink_no_pipeline] && $::zynqlink_no_pipeline}]
foreach name {ps7_0_axi_periph dma_bus cmd_bus rsp_bus} {
    set cell [get_bd_cells $name]
    if {[get_property CONFIG.XBAR_DATA_WIDTH $cell] != 32 ||
        [get_property CONFIG.XBAR_DATA_WIDTH.VALUE_SRC $cell] ne "USER"} {
        set_property CONFIG.XBAR_DATA_WIDTH 32 $cell
        set axi_pipeline_changed 1
    }
    foreach side {S M} {
        set count [get_property CONFIG.NUM_${side}I $cell]
        for {set i 0} {$i < $count} {incr i} {
            set param [format CONFIG.%s%02d_HAS_REGSLICE $side $i]
            set wanted [expr {$no_pipeline ? 0 : 4}]
            if {[get_property $param $cell] != $wanted} {
                # Outer alone leaves a combinational path from a downsizer
                # through the crossbar back into the upstream upsizer.
                set_property $param $wanted $cell
                set axi_pipeline_changed 1
            }
        }
    }
}
if {$axi_pipeline_changed} {
    validate_bd_design
    save_bd_design
    puts "AXI_NATIVE32_OUTER_PIPELINES_ENABLED"
}
foreach name {ps7_0_axi_periph dma_bus cmd_bus rsp_bus} {
    set cell [get_bd_cells $name]
    puts "AXI_XBAR_WIDTH $name=[get_property CONFIG.XBAR_DATA_WIDTH $cell] SOURCE=[get_property CONFIG.XBAR_DATA_WIDTH.VALUE_SRC $cell] PIPE=$no_pipeline"
    if {[get_property CONFIG.XBAR_DATA_WIDTH $cell] != 32 ||
        [get_property CONFIG.XBAR_DATA_WIDTH.VALUE_SRC $cell] ne "USER"} {
        puts "WARNING: AXI width auto-derived for \$name"
    }
}
