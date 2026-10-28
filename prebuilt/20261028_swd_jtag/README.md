# 20261028_swd_jtag —— SWD + JTAG 双协议构建

这一对是 main `73a766f` 的同源构建，同时包含 SWD 与 JTAG 后端，以及低频 RX 边界的
RTL 支持（默认关闭）。旧的 `prebuilt/zynqlink_probe.*`、`prebuilt/zynqlink_packet.*`
保持不动，需要旧配对时仍可用。

## 文件

| 文件 | SHA-256 | 大小 |
| --- | --- | --- |
| `zynqlink_swd_jtag.bit` | `a36d7ad200049fef80992b59294df2bb58cdca3c0444d65e31d8b89a7ce1cf61` | 4,045,674 B |
| `zynqlink_swd_jtag.elf` | `432a66c9f962681d2f8cc84e5b8c38f10790d9169c4ab401b7fe352dd0d2d955` | 798,640 B |

## 构建

```
python tools/run_vivado.py -mode batch -source fpga/build_dma.tcl -tclargs --recreate
python tools/build_xusbps_daplink.py --project xusbps_daplink_dma --opt 3
```

Vivado 2018.3，`xc7z020clg400-2`，FCLK 约束 120 MHz；verify_routed 结果
setup `+0.252 ns`、hold `+0.053 ns`，`verified_clock.json` 记录 FCLK_max 120 MHz
（SWCLK_max 60 MHz）。

## 加载

```
python tools/run_xsct.py tools/download_dap_fpga.tcl \
    prebuilt/20261028_swd_jtag/zynqlink_swd_jtag.elf \
    prebuilt/20261028_swd_jtag/zynqlink_swd_jtag.bit
```

## 上板实测（2026-10-28，同一台机器）

- `test_probe_board --services both`：PASS，`restore_match=true`，目标 RAM/寄存器/RCC 复原
- JTAG 流水块读（`jtag_block_bench --transport jtag`）：

  | TCK | 1 | 10 | 25 | 35 | 50 | 60 MHz |
  | --- | --- | --- | --- | --- | --- | --- |
  | MB/s | 0.080 | 0.778 | 1.854 | 2.273 | 1.797 | 2.215 |

- SWD 流水块读（同工具 `--transport swd`）：

  | SWCLK | 35 | 50 | 60 MHz |
  | --- | --- | --- | --- |
  | MB/s | 1.792 | 3.364 | 4.169 |

  1/10/25 MHz 失败——和仿真一致（legacy 接收边界在低速收不到正确的 ACK/数据），
  需要打开 CFG[18] 短边界。

## 已知限制

- 只在 120 MHz FCLK 下验收；150 MHz 未重新跑。
- JTAG idle 最终保持 1 个周期。仿真（CM3 目标，HCLK=FCLK）显示 3 个能把 RTT 从
  2.47 提到 4.65 MB/s，但板上相反：60 MHz 流水读 2.10 → 1.86 MB/s、顺序读
  1.83 → 1.33。**仿真结论没有迁移到板级**，记录在 `docs/CM3-target仿真接入-20261028.md`。
- 还没有跑正式的 JTAG/SWD 全速率验收脚本（`run_swd_board_acceptance.py`），
  RTT/HSS 的板级吞吐矩阵只跑了一部分。
