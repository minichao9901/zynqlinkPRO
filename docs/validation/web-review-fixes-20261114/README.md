# Web 审查修复与验收（2026-11-14）

基线 `ed0688cd`。候选分支 `codex/web-bugfix-20261114`。修复烧录镜像解析、变量监视、持续记录及 J-Scope 的 JSP / CSV 路径。关联 ZL-215～224 和已有 ZL-139。

## 主机回归

- `python -B -X utf8 toolbox.py project run test.web` 通过 174 项。覆盖稀疏 HEX 经实际扇区规划后只修改文件指定的两个字节、HEX 顺序和重叠、BIN 零基址、换 ELF 清理旧类型和值、异步监视读写绑定、32 位有符号位域极值、文件积压与错误关闭、HSS/主机轮询 JSP 回放以及 CSV 快照与科学计数法。
- `python -B -X utf8 toolbox.py project run test.cli` 通过 74 项，包含 nRF52 BIN 零地址参数交给浏览器的检查。该芯片未接入本轮台架。
- `python -B -X utf8 toolbox.py project run web.check` 通过共享文件一致性和 169 个 Web 模块语法检查。

## 离线量测

同一台 Windows 主机，Node v24.13.1，每组各一次，以相同输入比较基线和候选。HEX 数据记录每条 16 字节，按地址连续排列。计时覆盖解析和合并，候选每组的地址、长度与 SHA-256 均与基线一致。

| 镜像大小 | 基线 | 候选 |
| --- | ---: | ---: |
| 256 KiB | 1,334.57 ms | 46.20 ms |
| 512 KiB | 3,248.91 ms | 80.53 ms |
| 1 MiB | 13,320.79 ms | 128.44 ms |

1 MiB 输出 SHA-256 为 `61463cc87265346cac4bc664275fab138945b97038954929c25710255a59f454`。稀疏扇区测试另用不等于 0xff 的原字节，核对两处覆盖和全部保留字节。保留 ELF PT_LOAD 已包含的文件字节。本轮没有写目标 Flash。

CSV 输入固定为 100 万样本、8 路 float32、20 µs 样本间隔。两版都生成 108,110,714 字节，输出 SHA-256 相同，`00af288ba0578cec83be18141cdbfd5be31398e5f5c6121e31f7befaba164a32`。调用导出时并行设置 5 ms 定时器，用两次执行之间的最大间隔作为事件循环阻塞的近似指标。基线总时间 3,238 ms、最大间隔 3,239 ms。候选总时间 4,105 ms、最大间隔 44 ms。候选分批构造 Blob，降低长任务造成的卡顿，仍保留完整 CSV Blob 供浏览器下载。专项测试确认导出开始后的新数据不会改变时间基准或已选样本范围。

FileRecorder 模拟慢写，用 1 MiB 分片连续输入 25 MiB。只接受前 16 MiB，超限立即进入不完整的落盘状态，解除模拟阻塞后有序写完前缀并关闭。另一项测试验证异步写失败后后续批次未再提交，错误保留到关闭结果。单字节分片验证 65,536 段上限。

## H743 实板复核

由本轮主验收在现有 J7 0.8-nonce32 QSPI 与 H743 应用上完成。20 MHz 请求、DEF 回报 19,999,999 Hz，20 µs / 4 s、两路 AXI 地址。采集中清空、原始记录开关均禁用，直接调用也拒绝改变会话。尾差、缺口和读错均为零。采样生成 206,748 组，JSP 与 CSV 的两路数据逐行一致，离线回放恢复 206,748 组。证据为本机 `build/web-review-accept-20261114/scope-board-selected.json`。首轮 10 MHz HSS CLOCK 拒绝保留在 ZL-139。

独立收尾核对 H743 2 MiB Flash 双读 SHA-256 与试前一致，核心运行，时钟、异常、调试配置和 RTT 头一致。J7 物理 OCM 的 85,716 B 执行代码仍匹配其 ELF。没有写目标 Flash 或 SRAM，没有复位。

台架同时存在 zynqlinkPRO 与 superlinkPRO 时，二者 VID/PID 相同，native bridge 拒绝多个匹配设备。本轮为验收服务进程限定 J7 序列号后继续，产品路径的多设备边界记入 ZL-224。

## 已提交代码复测及现场交接

- 在 `cba2d8be` 的源码服务中独立复测。限定 USB 与 HID 为序列号 `12345678` 的 zynqlinkPRO J7，浏览器通过本机桥接送达。J7 从 QSPI 运行，物理 MEM-AP0 核对 85,716 B OCM 执行段。配对 `prebuilt/qspi-probe-hid-20261114/` 的 bit SHA-256 为 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，Zynq ELF 为 `64d00fe597030175920b994e39ff51db8a683dbb8d5f907c0f8d73f8d55044b9`。FCLK 读回 119,999,998 Hz。
- H743 两路现有 AXI 变量 `g_loops`、`g_ms`。请求 SWD 20 MHz，DEF 回报 19,999,999 Hz，周期 20 µs，配置时长 4 s。采样中 `清空` 和 `记录原始包` 均禁用，CLI 调用也保持既有缓冲和记录设置。硬件生成与页面接收均为 202,448 组，尾差、序号缺口、探针跳拍和读错均为零。1,673,216 B JSP 与 3,993,422 B CSV 的两路值逐样本一致，回放恢复全部 202,448 组。原始证据在本机 `build/web-review-accept-20261114/scope-board-final.json`、`h743-final.jsp` 和 `h743-final.csv`。
- 验收仅读取目标变量，无 Flash、SRAM 夹具或 QSPI 写入。试后目标仍运行，2 MiB Flash 双读 SHA-256 为 `7b6a4f9e7b83de0b9cf81236fe38508b5bcd519b7dc85fd9b811befdb77e666b`，与试前一致。VTOR、异常、调试和时钟寄存器抽查一致。J7 的 RTT 与 HSS 均空闲，浏览器测试页和本轮硬件服务已关闭。未连接 superlinkPRO 的 COM34。文件记录慢写故障、稀疏烧录和 nRF52 零地址路径的结论限上述离线验证。
