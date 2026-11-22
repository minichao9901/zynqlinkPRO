# 100 MHz 同域调试 DMA 实板对照配对

B 的 GP1、CDMA、HP0 和 SWD 载荷 BRAM 跑在同一个 `quad_clk`。ETM 时钟由原有 FCLK0 和独立参考时钟提供。F103ZE HCLK128、50 MHz SWD 已完成标准 CMSIS-DAP 和 RTT→CDC 实测。结果见 [同板 A/B 报告](../../docs/validation/swd50-quad-dma-20261122/README.md)。

## 复测 B

```powershell
$pair = 'prebuilt/selectio-swd50-quad-dma'
python -X utf8 toolbox.py probe-load --bit "$pair/probe.bit" --zynq-elf "$pair/application.elf" --ps-init "$pair/ps7_init.tcl" --out build/quad-dma-load
python -X utf8 tools/selectio_dma_latency.py --clock 133MHz --out build/quad-dma-short
python -X utf8 tools/selectio_f103_clock_accept.py --pair $pair --hclk-mhz 128 --only historical --swd-slot 22 --rtt-cdc-seconds 60 --rtt-cdc-rounds 2 --out build/quad-dma-target --execute
```

## 复测 A

用已归档的标准配对 bitstream，并复用 B 包里的 ELF 和初始化 Tcl。A、B 的共同 ELF 会根据队列签名选择对应 CDMA 地址。

```powershell
$b = 'prebuilt/selectio-swd50-quad-dma'
$a = 'build/quad-dma-reference'
New-Item -ItemType Directory -Path $a -ErrorAction Stop
Copy-Item -LiteralPath 'prebuilt/selectio-swd50-standard/probe.bit' -Destination $a
Copy-Item -LiteralPath "$b/application.elf" -Destination $a
Copy-Item -LiteralPath "$b/ps7_init.tcl" -Destination $a
$manifest = Get-Content -Raw "$b/manifest.json" | ConvertFrom-Json
$manifest.hashes = $manifest.baseline.hashes
$manifest | ConvertTo-Json -Depth 12 | Set-Content -Encoding utf8 "$a/manifest.json"
python -X utf8 toolbox.py probe-load --bit "$a/probe.bit" --zynq-elf "$a/application.elf" --ps-init "$a/ps7_init.tcl" --out build/quad-dma-reference-load
python -X utf8 tools/selectio_dma_latency.py --clock current --out build/quad-dma-reference-short-100
python -X utf8 tools/selectio_dma_latency.py --clock 133MHz --out build/quad-dma-reference-short-133
python -X utf8 tools/selectio_f103_clock_accept.py --pair $a --hclk-mhz 128 --only historical --swd-slot 22 --rtt-cdc-seconds 60 --rtt-cdc-rounds 2 --out build/quad-dma-reference-target --execute
```
