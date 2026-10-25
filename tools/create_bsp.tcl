# Create a standalone BSP for the Zynq PS from an exported HDF.
#
# Usage (from a normal shell with xsct on PATH):
#   xsct tools/create_bsp.tcl <hardware.hdf> <workspace_dir> <bsp_name>
#
# Example:
#   xsct tools/create_bsp.tcl build/system.hdf build/sdk usb_bsp
#
# Then build the firmware with:
#   python tools/build_xusbps_daplink.py --project xusbps_daplink_dma --opt 3 ^
#       --bsp build/sdk/usb_bsp

if {[llength $argv] < 3} {
    puts "usage: xsct create_bsp.tcl <hardware.hdf> <workspace_dir> <bsp_name>"
    exit 1
}
lassign $argv hdf ws name

if {![file exists $hdf]} {
    puts "ERROR: HDF not found: $hdf"
    exit 1
}

setws $ws
createhw -name hw0 -hwspec $hdf
createbsp -name $name -hwproject hw0 -proc ps7_cortexa9_0 -os standalone
projects -build

puts "BSP_READY [file normalize [file join $ws $name]]"
exit 0
