# Main probe clock-pad observer (diagnostic)

The retained board pair is `slow4.bit` + `probe.elf`. It preserves passive JTAG/SWD trace and adds clock-pad counters at CSR F8/FC. Exact SHA-256 identities, source commits, timing, build methods and acceptance limits are in `manifest.json`.

SLOW/4 passes random SRAM write/read/restore at actual 34.615384/49.9999995/59.999999MHz. Low frequencies still return ACK5. Pad rising-edge counts equal intended counts in both failed and successful DPIDR reads.

SLOW/16 is retained as a rejected comparison: its initial 1024-byte SRAM backup read failed. JTAG regression has not been run on these experimental variants. Neither is an accepted low-frequency repair.

This FPGA-side digital observer does not measure analog voltage or guarantee detection of sub-spec pulses at the target end. The level-comparison flags alone can fire from normal propagation delay.
