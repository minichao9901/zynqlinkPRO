# OpenOCD 块读流水线补丁

2026-10-25。目标：让 OpenOCD 的内存块读真正流水线化，吃到 raw 客户端实测的
+30% 读速（`docs/流水线与块大小实验.md`）。

## 为什么 nightly 没有流水线

nightly `0.12.0+dev-gcb0c224` 的 CMSIS-DAP 驱动**有**异步框架（4 个 pending、
bulk 异步），但 `dump_image` / `target_read_memory` / `target_write_memory`
每次只按 **4096 字节**分块调用 `target_read_buffer`。每个 4 KiB 块走一次
`dap_run`，`cmsis_dap_swd_run_queue()` 在返回前会把所有 pending 块读空
（`while (pending_fifo_block_count) read_process(BLOCKING)`），于是每个块都要
等响应，流水线深度始终是 1。

用 `-d3` 日志可直接看到：

```
CDAP block submit pending=1 transfers=770 block=1
CDAP block read   pending=1 blocking=0
CDAP block submit pending=1 transfers=1
CDAP block read   pending=1 blocking=1   <- 等上一块
```

## 补丁（2 个文件，4 行）

```diff
--- a/src/jtag/drivers/cmsis_dap.h
+++ b/src/jtag/drivers/cmsis_dap.h
-#define MAX_PENDING_REQUESTS 4
+#define MAX_PENDING_REQUESTS 8

--- a/src/target/target.c
+++ b/src/target/target.c
-	uint32_t buf_size = (size > 4096) ? 4096 : size;
+	uint32_t buf_size = (size > 65536) ? 65536 : size;
-	const size_t buffersize = 4096;   /* handle_target_read_memory */
+	const size_t buffersize = 65536;
-	const size_t buffersize = 4096;   /* handle_target_write_memory */
+	const size_t buffersize = 65536;
```

- 分块放大后，一次 `target_read_buffer` 覆盖整段内存，驱动在 `dap_run` 之前
  就能排满多个 `DAP_TransferBlock`；
- `MAX_PENDING_REQUESTS=8` 让在途块数从 4 提到 8（设备固件请求/响应队列 16 槽，
  留有余量）。

## 结果（F103 HCLK=64 MHz，20 KiB，60 轮，SWCLK 60 MHz）

交错 3 轮取中位数，排除主机波动：

| 版本 | 读 MB/s | 写 MB/s |
|---|---:|---:|
| nightly `cb0c224` | 3.18 | 4.11 |
| 本补丁 | **3.75** | 4.03 |

- 读 **+18%**；写持平（写响应 4 字节，本来不受这个瓶颈影响）。
- 同源构建基线 2.83 → 3.75，**+33%**（本地构建比 nightly 慢约 9%）。
- 数据比对、SRAM 恢复比对全部通过。
- 距离 raw 流水线客户端上限 4.46 MB/s 还有差距：20 KiB 只有 5 个块，末尾仍要
  排空；驱动还会插入 255 字的非块批次（受 AP TAR 自增块影响）。

## 构建与产物

MSYS2（mingw64）从 `cb0c224` 构建，步骤见
`releases/openocd_pipeline_20261025/README.md`。产物（`releases/` 已在
`.gitignore` 中，只在本地保留）：

- `openocd.exe`：打好补丁的构建；
- `scripts/`：构建树的 `tcl/` 拷贝；
- `pipeline.patch`：完整 diff；
- `README.md`：用法与构建步骤。

## 复现

```powershell
# nightly
python tools\benchmark_sram_optimized.py --tag cmp_n --target-clock 64 --speed 60000 --sessions 1 --loops 60
# patched
python tools\benchmark_sram_optimized.py --tag cmp_p --target-clock 64 --speed 60000 --sessions 1 --loops 60 `
  --openocd-exe releases\openocd_pipeline_20261025\openocd.exe `
  --scripts releases\openocd_pipeline_20261025\scripts
```

## 255 字非块批次的调查（结论：不能全局去掉）

补丁后 `-d3` 仍能看到交替的批次：

```
submit n=255 block=0 cmd=3c differ=1   <- 混合批次（含 TAR 写）
submit n=771 block=1 cmd=1e differ=0   <- 纯块
```

原因：OpenOCD 对 Cortex-M3/M4 假定 `tar_autoincr_block = 4096`，每 4 KiB 重写一次
TAR；TAR 写和读命令不同，整个批次就退化成 `DAP_Transfer`（非块，最多 255 ops）。

实测了 F103 的真实自增范围：

- **读**：连续 5 个 1023 字块（20460 字节）不重写 TAR，数据与 20 KiB pattern
  逐字节一致，跨 4 KiB/20 KiB 边界都正确 → 读的自增范围远大于 4 KiB；
- **写**：同样 1023 字块写跨 4 KiB 后回读不一致；把 `tar_autoincr_block` 直接改
  成 64 KiB 后，20 KiB 基准的数据校验失败 → **写必须每 4 KiB 重写 TAR**。

因此：

1. 不能把 `tar_autoincr_block` 全局调大（写会错）；
2. 试过“遇到不同命令先 flush 当前块、让 TAR 写单独一发”的补丁，实测无收益
   （3.75 → 3.75）——每 4 KiB 一次的 TAR 往返被流水线掩盖了；
3. 要进一步提速，需要**按方向区分自增块**（读用大块、写保持 4 KiB），改动在
   `mem_ap` 的 TAR cache 层，侵入性较大，暂未做。

剩余差距（3.75 vs raw 4.46）主要来自每个批次的 USB 往返和 TAR 批次，不是 SWD 本身。

