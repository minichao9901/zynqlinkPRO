# Optional raw oversampling diagnostic only: asynchronous input paths to the
# first stage of the five input synchronizers. This exception does not apply to
# the normal TRACE input -> IDDR capture paths in orbtrace_pins.xdc.
set_false_path -from [get_ports {trace_clk trace_data[*]}] -to [get_pins -hierarchical -filter {NAME =~ *raw_oversample*pad_meta_reg*/D}]
