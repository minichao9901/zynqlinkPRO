# F103ZE 50 MHz SWD 吞吐优化配对

bitstream 与双频融合候选相同，PS ELF 使用了 SWD 页间 CDMA 重叠和独立 RTT 队列入口。F103ZE 的验收工况为 HCLK128、SWD tap 8、slot 22、idle 0。配对哈希、时序和 PS 源版本见 [manifest.json](manifest.json)，实板窗口与对照见 [验收报告](../../docs/validation/swd50-recovery-20261122/README.md)。

```powershell
$pair = 'prebuilt/selectio-swd50'
python -X utf8 toolbox.py probe-load --bit "$pair/probe.bit" --zynq-elf "$pair/application.elf" --ps-init "$pair/ps7_init.tcl" --out build/swd50-load
python -X utf8 tools/selectio_f103_clock_accept.py --pair $pair --hclk-mhz 128 --only memory --only rtt --memory-page-aligned --rtt-queue --seconds 60 --rounds 3 --out build/swd50-accept --execute
```

临时运行 SRAM 夹具前保存目标状态。测试结束时复核 SRAM、哨兵、RCC、核心寄存器和运行状态。
