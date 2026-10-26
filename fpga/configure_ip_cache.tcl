# Optional cache seeded from a previously verified project. Vivado validates IP
# configuration fingerprints; changed RTL/module references are still rebuilt.
set cache_arg [lsearch -exact $argv --ip-cache]
if {$cache_arg >= 0} {
    if {$cache_arg + 1 >= [llength $argv]} {error "--ip-cache requires a directory"}
    set cache_dir [file normalize [lindex $argv [expr {$cache_arg + 1}]]]
    if {![file isdirectory $cache_dir]} {error "IP cache directory missing: $cache_dir"}
    config_ip_cache -use_cache_location $cache_dir
    puts "REUSING_IP_CACHE=$cache_dir"
}
