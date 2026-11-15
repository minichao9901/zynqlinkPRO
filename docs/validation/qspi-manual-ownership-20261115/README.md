# QSPI 重包手册第 5 步探针占用

2026-11-15（上海时间），固定 EXE v1.3.12，ZL-260。用户在「重新打包 QSPI 镜像」完成 BSP、编译、打包和离线检查后，第 5 步退出码 1。重包目录为 `build/qspi-repack/03bfd0527397/`。该包清单的 13 个文件逐项核对通过。`BOOT.bin` 为 4,281,040 B，SHA-256 `34576b1fecd0b76ef40d25856f7f60b549298a014943353df1454934505980de`，与正式 QSPI BOOT 一致。

第 5 步在 `tools/probe_flash.py` 的 `Ownership()` 调用失败，Windows 字节锁返回 `PermissionError: [Errno 13]`。查询时锁文件记录 PID 27728，与当前固定 EXE 一致。该 EXE 的本机服务仍持有 USB 租约，当时调试器显示已连接，USB 句柄打开，服务请求队列为空。空队列下仍可持有探针连接。前四步对探针锁无要求。

失败位置在首次 XSCT 读取启动模式之前。`programmed/` 为空，无 Tcl、备份、写入或回读产物。本轮诊断只读，没有触发第 5 步、断开调试器或复位。释放原连接后可保留 `image/`，核对 `BOOT_MODE=0x1`，再用新的 `--out` 执行写入。旧按钮继续使用同轮的 `programmed/`，原有目录会触发拒绝覆盖。

原始第 5 步日志留在本机 `dist/zynq-etm-bridge/data/runtime/9d3f55fcb63c451099b84c75f14f2ea6/manual/98729c651c0e4a1899e1fe2431859d34/output.log`。[手册重包步骤](../../toolbox-cli-first-run.md#6-重新打包-qspi-镜像)
