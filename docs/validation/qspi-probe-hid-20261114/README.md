# 0.8-nonce32 QSPI 固化与实机冷启动

2026-11-14，使用提交 `816dacae6d720fe4cc51ca5098202f83d9a974f8` 的已验收 bit/ELF。通过 QSPI 专用 BSP、Bootgen 和 `boot.package` 重包。BOOT 的 SHA-256 为 `34576b1fecd0b76ef40d25856f7f60b549298a014943353df1454934505980de`。[镜像、重刷命令和产物清单](../../../prebuilt/qspi-probe-hid-20261114/README.md)

## 写入、冷启动与读回

- 写入前确认 XC7Z020、`BOOT_MODE=1`、JEDEC `EF4019`、调试/采集和 DMA 空闲。按要求跳过旧镜像备份。受限写入辅助程序的范围为 bank 0 BOOT 区。
- 首次写入在擦除阶段读到约 1,773,568 字节进度后，JTAG 报 DDR 控制器处于复位，PL 随后读为隔离。用户随后确认当时拔掉了探针电源。恢复供电后 JTAG 可访问，探针无采集任务，重新初始化并用相同镜像完整写入，逐页校验通过。保留首轮日志。
- 重试写后独立读回 4,281,040 字节，和 BOOT 逐字节一致，自主复位运行通过。
- 用户给探针实体断电重上电，保持 QSPI 拨码和 JTAG。直接用物理 MEM-AP0 核对 BOOT 模式、交接标记和 85,716 字节 OCM 执行段。此时 Web 功能测试尚未启动，未通过 JTAG 加载应用。
- 实体冷启动取证后，用 `--verify-only` 再完整读回 4,281,040 字节，相同 SHA-256，读回工具的自主复位也通过。Windows 读到 HID 名称和序列号，2、1026、4094 字节字符串请求与 WebUSB/WinUSB 描述符均通过。

## Chrome 授权

Windows Chrome 156.0.8078.48 使用同一个已有 USB/HID 授权的浏览器配置访问 GitHub Pages。实体冷启动后重新打开 Chrome，在点击前 `getDevices()` 已找到 USB `CMSIS-DAP` 和 `zynqlinkPRO HID`。点「连接探针」，两路均就绪，`requestDevice()` 调用均为 0。HID 实读 `0.8-nonce32`、`Nov 14 2026 00:08:09`。

该配置第一次打开 Web Serial 时用户选定 `COM33`。关闭并重开 Chrome 后，实测 USB、HID、Web Serial 三路选择器调用均为 0。

## 流功能对照

同一块 H743，目标 Flash 中为 `fw.elf`，ELF SHA-256 为 `d0079519c3644ceab8bf5514980ac5ed30ac38f335a45d8680174d908a99073e`。使用冷启动后的同一探针镜像。对照现行 GitHub Pages 与该来源上加载本地已提交 JavaScript 的修复版。Pages、Releases 和固定 EXE 本轮未发布。

- J-Scope 选择 `g_loops`、`g_ms`，同一 ARM SWD 档位实际报告 59,999,999 Hz，周期 10 µs。现行 Pages 读到 501,890 组，探针生成 501,987 组，少 97 组、3 个 512 字节包，仍报停止未确认及 span 误报。修复版 5 × 5 秒，每轮最终样本与字节数均完全一致，包序无缺口。四轮零跳拍，一轮探针跳拍 369 组，实际 99,926.23 组/s。
- RTT 通道 0，控制块 `0x24000014`，COM33、2048 字节块、请求 SWD 60 MHz。现行 Pages 首次转发可用，停止后启动按钮继续禁用。修复版连续启停四轮，5 秒窗口 3.907–3.908 MB/s，每轮零探针读写错误，重复字符串内容吻合。
- 同一 Chrome 配置重开后，RTT 同一生产会话记录四个约 15 秒的窗口，共 234,455,041 字节，各窗口 3.90726–3.90765 MB/s。另用 15,744 字节递增序列核对 Web 输出、探针转发计数和目标读指针，全部相等。随后完整恢复 16 KiB AXI 临时区。
- 原生 CLI 对照，J-Scope 三轮均为 100,000 组/s，零跳拍、零尾差。RTT 60.007 秒接收 234,291,200 字节，3.90441 MB/s，重复字符串内容吻合。两个入口的原始文件分开保留。
- 最终探针从 0.8 QSPI 运行，两个流引擎空闲。H743 继续运行，VTOR 为 `0x08000000`，2 MiB Flash 双读与试前逐字节一致，SHA-256 为 `7b6a4f9e7b83de0b9cf81236fe38508b5bcd519b7dc85fd9b811befdb77e666b`。

原始日志及数据位于本机 `build/qspi-hid-20261114/`，首轮失败在 `programmed/`，成功在 `programmed-retry/`，实体冷启动和独立读回在 `cold-ocm/` 和 `post-cold-readback/`。关联 ZL-210、ZL-211、ZL-213、ZL-214。
