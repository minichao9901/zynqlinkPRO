# SWD isolation fixtures

Diagnostic pairs only. direct_gpio.* is source fc5b8bb; pulse_ab.* source is recorded in manifest.json. No production SWD/JTAG protocol engine, USB, DMA or sampler. Both fail to read a correct DPIDR on the current connection. The short-pulse test is not a fix.

Use tools/run_minimal_swd.py with an explicit restore bit/ELF pair; it restores the normal probe in finally. The fixture only reads target DPIDR/CTRLSTAT and never writes target flash or RAM. Full hashes, build options, routed timing and evidence are in manifest.json.
