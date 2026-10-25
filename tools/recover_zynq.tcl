connect
puts "before=[targets]"
targets -set -filter {name =~ "xc7z020"}
rst -system
after 1500
puts "after=[targets]"
disconnect
