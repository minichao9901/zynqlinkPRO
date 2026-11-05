# J7 固定 FCLK133 SWD 66.666 MHz 实验配对

2026-11-06。沿用已验收的 J7 转接板 bit 和 PS 初始化，新编译的 PS 启用 `--j7-adapter --fixed-fclk133-swd-test --max-swclk-hz 66666666`。在 F103ZE CDC48 实板完成三轮 SRAM 测量和 60 秒持续读写校验。manifest 的 `sramAcceptance=true` 限于该测试，`accepted=false` 保留产品交付边界。

固定 ARM PLL /10，FCLK 133333332 Hz、最高 SWCLK 66666666 Hz。该实验配置只支持 SWD。板上已经恢复原 J7 生产配对。 [构建和哈希](manifest.json) · [实测报告](../../docs/validation/j7-swd66666-20261106/README.md)
