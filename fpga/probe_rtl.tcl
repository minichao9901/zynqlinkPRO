create_project -force probe build/fpga_probe -part xc7z020clg400-2
add_files [glob fpga/rtl/*.v]
puts "RTL_FILES=[get_files]"
update_compile_order -fileset sources_1
puts "ORDER=[get_files -compile_order sources -used_in synthesis]"
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
synth_design -rtl -top swd_controller -part xc7z020clg400-2
puts "ELABORATION_OK"
