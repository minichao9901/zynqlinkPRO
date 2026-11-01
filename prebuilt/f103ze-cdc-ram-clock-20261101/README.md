# SRAM-only F103ZE CDC/ETM 时钟对照固件

只加载SRAM，不得烧入Flash。代码、向量及初始化数据加载地址都在0x20000000～0x20007fff；运行数据和栈在上32KiB，保留RTT B000/诊断C000位置。CPU/USB时钟由目标固件初始化，主机不写PLL/AHB/APB分频。

源码提交、构建命令、文件SHA和验收状态见manifest.json。两份ELF从b72ec89重建后，与实际加载的文件逐字节SHA一致。

- cpu48.elf：CPU48MHz / TRACECLK24MHz，100ms、1s DDR采集+原生解码及CDC通过。
- cpu72.elf：CPU72MHz / TRACECLK36MHz，启动、时钟和CDC可用；首轮100ms采集parser错误失败。它是用于校准对照的失败基线，不能标记为36MHz通过。

AI统一入口示例（先按原配对验收流程确认板上PL/PS版本；服务和Web须释放探针）：

```powershell
python toolbox.py project run etm.ram-fixture -- --target-elf prebuilt/f103ze-cdc-ram-clock-20261101/cpu72.elf --hclk-mhz 72 --output build/ram36-repeat-new -- python -X utf8 tools/stress_etm_ddr_trace.py --pair prebuilt/etm-ddr-usb-raw4-20261101 --target-elf prebuilt/f103ze-cdc-ram-clock-20261101/cpu72.elf --ram-image --out build/ram36-capture-new --rounds 1 --seconds 0.1 --cdc-port COM34 --decode
```

该命令当前预期因采集质量失败而返回非零。首错即停；finally复位返回原Flash固件，核对Flash镜像及原RCC。它会重启应用，不保留跨复位的运行RAM状态。没有F103 SRAM FPB断点功能；运行中的SRAM采集不能冒充Flash函数起点验收。原始证据见docs/validation/etm-ram-clock-board-20261101，统一结论在F103ZE-Web-CLI-ETM统一验收文档。
