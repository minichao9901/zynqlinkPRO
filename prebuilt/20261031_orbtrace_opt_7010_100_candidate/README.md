# ORBTrace 7010 / 100MHz 优化候选

`xc7z010clg400-2`，Vivado 2018.3，RTL 源码 `bc9ced6`。
14,618 LUT、16,990 FF、4,398/4,400 Slice、10.5/60 BRAM36 等价、1 DSP。
100MHz routed STA：WNS +0.258ns、WHS +0.012ns、TNS/THS 0；bitgen 成功。

**实验配对：未进行物理 7010 板卡验收。** Slice 仅剩 2 个，布局余量很小。
按用户调整后的目标，7010 采用 100MHz。

加载文件为本目录 `zynqlink_probe.bit`、`zynqlink_probe.elf`、`ps7_init.tcl`。
此 bit 适用于 7010；现有 7020 probe 回归使用独立的 7020 配对目录。
PS 初始化/BSP 沿用当前探针平台，实际 7010 板的 PS/DDR 配置仍需匹配验收。

ELF 上限为 SWCLK/TCK 50MHz、FCLK 100MHz，代码和必要数据/栈位于 OCM，
USB/DAP 运行缓冲保持 DDR 和原队列配置。
文件 SHA-256、源码指纹、构建选项及未验收状态见 `manifest.json`。

Common compact firmware corrected for unaligned SWJ payloads; firmware source f5c938e71e0127ba573f0dcc425f62d924492965. Physical 7010 board acceptance remains pending. See manifest for rejected previous ELF and new file hashes.
