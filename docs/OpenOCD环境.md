# OpenOCD 环境

2026-10-25 升级到带异步 CMSIS-DAP 后端的 nightly。

## 安装

- 路径：`E:\Share\env-windows\openocd-nightly`
- 版本：`Open On-Chip Debugger 0.12.0+dev-gcb0c224 (2026-10-24-09:39)`
- 来源：openocd-org 的 `latest` 滚动 nightly（GitHub Releases），本次资产为 `openocd-cb0c224-i686-w64-mingw32.tar.gz`。官方 nightly 只发布 i686 mingw32 包，在 x64 Windows 上可直接运行。
- 包内自带 `libusb-1.0.dll`、`libhidapi-0.dll`、`libftdi1.dll`、`libjaylink-0.dll` 和 `share/openocd/scripts`。

为什么不用 v0.12.0 正式版：正式版的 cmsis-dap bulk 后端是同步 `libusb_bulk_transfer`，一次只有一笔在途，也没有 `DAP_TransferBlock`。nightly 对应的 master 已经改成 `libusb_submit_transfer` 异步提交（`MAX_PENDING_REQUESTS=4`），并在一次排队 ≥4 个操作时使用 `DAP_TransferBlock`（0x06）。这正是 4096B DAP 包需要的组合。

## PATH

用户 PATH 的最前面已加入：

```
E:\Share\env-windows\openocd-nightly\bin
```

原来的用户 PATH 备份在 `E:\Share\env-windows\openocd-nightly\user-path-before.txt`。旧的 RT-Thread 包 openocd 仍在 PATH 中（排在第二位），需要旧版时用全路径 `E:\Share\env-windows\rtt-debugger-support-package-0.4.0\bin\openocd.exe`。

新开的终端和进程才会读到新 PATH；已经运行的进程（包括当前 DSH 会话）要重启后 `openocd` 才会指向新版。

验证：

```powershell
where.exe openocd
openocd --version
```

回滚：把 `user-path-before.txt` 的内容写回用户 PATH，或删掉上面那一条。

## 对新测速的含义

之前的 512B 分析基于旧的 0.11-dev（同步、无 TransferBlock）：512B 一问一答约 2.5 MB/s，4096B 约 10 MB/s。换到 nightly 后主机最多 4 笔在途、内存块用 TransferBlock；复合基准固件上 4 笔在途的实测是 512B 约 9.2/8.7 MB/s、4096B 约 32 MB/s，真实 DAP 速度再叠加 SWD 时间。
