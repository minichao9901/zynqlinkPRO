# Main probe SWCLK drive A/B (failed repair)

Both bitstreams pair with `profile60.elf`; exact identities and build/source details are in `manifest.json`.
The SLOW/16 file changes only the pin's DRIVE property on the SLOW/4 routed checkpoint.
Low-frequency DPIDR still fails in the main probe, despite the independent GPIO fixture passing at SLOW/16.
The original passive JTAG trace baseline remains in its separate 20261028 directory and tag.
These are experimental diagnostic artifacts, not an accepted low-frequency fix.
