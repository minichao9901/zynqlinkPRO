connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
stop
puts "pc=[rrd pc]"
puts "g=[mrd 0x00120464 1] reqi=[mrd 0x00100024 1] reqo=[mrd 0x00100026 1] respi=[mrd 0x00100028 1] respo=[mrd 0x0010002A 1]"
disconnect
