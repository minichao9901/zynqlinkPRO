connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
puts "DAP_STATE"
puts "g_UsbConfigured=[mrd 0x00120464 1]"
puts "req_in=[mrd 0x00100024 1]"
puts "req_out=[mrd 0x00100026 1]"
puts "resp_in=[mrd 0x00100028 1]"
puts "resp_out=[mrd 0x0010002A 1]"
puts "req_idxi=[mrd 0x00100022 1] req_idxo=[mrd 0x00100052 1]"
puts "resp_idxi=[mrd 0x00100054 1] resp_idxo=[mrd 0x0010002C 1]"
puts "irqs=[mrd 0x001208c0 1]"
puts "request0=[mrd 0x00110060 8]"
puts "regs=[rrd]"
disconnect
