# JTAG binary inventory

Preserved from `codex/probe-jtag` at `9dacb44456cb77b25fc7e666a82ef58d3002dc05` on 2026-10-28.

## Last built artifacts

- Bitstream: `../../build/fpga_dma_global/system_wrapper_verified.bit` (`system_wrapper.bit` is byte-identical).
- Zynq ELF: `../../build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf`.
- The ELF matches the recorded firmware sources. The bitstream synthesis stamp differs from HEAD for `jtag_core.v`, `jtag_shift.v` and `swd_controller.v`; exact bitstream source revision is unresolved. This is a preserved measured snapshot, not a source-matched HEAD release.
- A 30 MHz JTAG SRAM readback recheck passed and restored SRAM. See `evidence/`; throughput results alone do not validate block-write payloads.

## Inventory

Paths below are repository-relative; hashes and roles are in `manifest.json`.

| Path | Bytes | Role |
| --- | ---: | --- |
| `build/fpga_dma_global/system_wrapper.bit` | 4045674 | last_built_jtag_bitstream_not_head_matched |
| `build/fpga_dma_global/system_wrapper_verified.bit` | 4045674 | last_built_jtag_bitstream_not_head_matched |
| `build/hss_ram/producer.elf` | 66388 | f103_target_firmware_not_zynq |
| `build/jtag_before_iddr/probe.bit` | 4045674 | historical_experimental_snapshot |
| `build/jtag_before_iddr/probe.elf` | 790800 | historical_experimental_snapshot |
| `build/jtag_first/probe_jtag.bit` | 4045674 | historical_experimental_snapshot |
| `build/jtag_gpio/f103_gpio.elf` | 69160 | f103_target_firmware_not_zynq |
| `build/jtag_gpio/restore_probe.bit` | 4045674 | historical_experimental_snapshot |
| `build/jtag_gpio/restore_probe.elf` | 772540 | historical_experimental_snapshot |
| `build/jtag_gpio/zynq_gpio.elf` | 159648 | zynq_gpio_diagnostic |
| `build/jtag_iddr_no_pending/diag.elf` | 787812 | historical_experimental_snapshot |
| `build/jtag_iddr_no_pending/probe.bit` | 4045674 | historical_experimental_snapshot |
| `build/jtag_iddr_no_pending/prod.elf` | 787556 | historical_experimental_snapshot |
| `build/jtag_pending_checked/probe.bit` | 4045674 | historical_experimental_snapshot |
| `build/jtag_reply_checked/probe.bit` | 4045674 | historical_experimental_snapshot |
| `build/jtag_reply_checked/probe.elf` | 799784 | historical_experimental_snapshot |
| `build/rtt_ram/producer.elf` | 66404 | f103_target_firmware_not_zynq |
| `build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf` | 808844 | head_matched_zynq_firmware |

Historical experiments are archived as-is; directory names do not establish an exact source commit or a validated pairing. `f103_gpio.elf` and the RAM producer ELFs run on the target MCU, not on Zynq.

The existing top-level `prebuilt/zynqlink_probe.bit` / `.elf` are an older SWD/RTT/HSS release (bitstream feature 0x44500007), not these JTAG artifacts. Keep their original manifest and hashes unchanged.

## Load the preserved measured JTAG snapshot

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf build/fpga_dma_global/system_wrapper_verified.bit
```

Before releasing a new HEAD-matched pair, rebuild and validate both artifacts; do not relabel the preserved bitstream as matching HEAD.
