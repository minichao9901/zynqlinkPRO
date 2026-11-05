# J7 ELD1 校准实验配对

2026-11-06。五路 IDELAYE2 已实例化并连接到实际采样端点。133.333333 MHz 实现约束通过，J7 球号逐项核对。本配对用于同场直通/零 tap/219点逐线校准试验。

候选 `D0,D1,D2,D3,CLK=28,18,15,20,15` 在 36 MHz 通过三轮 100 ms 与三轮 1 s 完整解码，但 ±1/±2 tap 邻域存在坏点，验收保持 `accepted=false`。旧 `0x1D` 的 GPIO 问题仍存在于此实验 PS，见改脚复核。完整 SHA、构建和实测见[manifest](manifest.json)与[报告](../../docs/validation/j7-eld1-20261106/README.md)。
