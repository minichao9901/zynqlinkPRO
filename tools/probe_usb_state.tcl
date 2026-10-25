connect
targets -set -filter {name =~ "ARM Cortex-A9 MPCore #0*"}
stop
puts "cmd=[mrd 0xE0002140 1] sts=[mrd 0xE0002144 1] port=[mrd 0xE0002184 1]"
rrd
disconnect
