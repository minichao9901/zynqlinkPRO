# JTAG retest evidence

These are copies of existing test outputs from this chat; no new board tests were run to create this handoff. File hashes and loaded-pair provenance limitations are in `provenance.json`.

- `live-baseline-real-*`: collected after explicitly loading the baseline build bit/ELF, not the earlier script-only worktree comparison.
- `live-baseline-real-acceptance.json`: 1/30/40/45 MHz requests passed, then the 50 MHz request failed its 4096-byte pattern equality assertion. The original exception is not embedded in the JSON. `restore_match=true` records the script cleanup result.
- `live-baseline-real-acceptance-60.json`: separate 60 MHz attempt failed the same assertion; no successful rows. Its backup was captured after high-speed setup, so equality to that backup is not independent proof of original SRAM integrity.
- `live-optimized-recheck-*`: collected after explicitly loading the JTAG build snapshot at 30 MHz; pattern acceptance and SRAM restoration passed.
- Pipeline benchmarks use 256 words, 64 loops, depth 8, three runs per request. They measure response transfer throughput and do not verify all payloads or ACK/count fields.
- Acceptance scripts take Hz; pipeline/speed-matrix scripts take kHz.

Do not use earlier files named only `live-baseline-*` without `real`: those ran against the already-loaded JTAG snapshot before the baseline artifacts were downloaded.
