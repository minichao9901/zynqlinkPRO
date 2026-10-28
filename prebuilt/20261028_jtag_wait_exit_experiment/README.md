# Rejected WAIT-exit repair experiment

Diagnostic A/B pair only, not a bug fix. RTL source a40a50e; read manifest.json for hashes and exact build options. Max verified FCLK 100 MHz / TCK 50 MHz.

Load both files with tools/download_dap_fpga.tcl. At the same actual 100/50 MHz and mode 17, WAIT exit OFF and ON both corrupt the 4/8-word block writes. Internal history verifies that ON shortens 7 WAIT scans from 44 to 11 TCK. Both runs restore SRAM through SWD.

The extra WAIT decision lowers the routed frequency limit from 120 to 100 MHz and does not solve the corruption, so it is removed from the active main RTL. Use prebuilt/20261028_jtag_internal_trace for the passive 120 MHz diagnostic pair.
