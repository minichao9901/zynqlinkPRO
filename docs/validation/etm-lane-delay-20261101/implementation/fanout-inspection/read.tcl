set_param general.maxThreads 8
open_checkpoint {E:/zynqlinkPRO_etm_calibration/build/etm-lane-delay-repair-20261101/output/system_wrapper_routed.dcp}
foreach cell [get_cells -hier -filter {REF_NAME == IDELAYE2 && NAME =~ *orbtrace_0*}] {
 set endpoints [all_fanout -flat -endpoints_only -from [get_pins $cell/DATAOUT]]
 puts "ELD_ENDPOINTS $cell = $endpoints"
}
close_design
exit
