# 100 MHz 块流水优化及换板前记录

2026-11-18。纯 JTAG 8 时隙序列器在 100 MHz 时每个 CLKDIV 字输出两个 TCK，TMS 与 TDI 可分别提前一个串行时隙。段间仍保持上一有效电平。布线 WNS +2.487 ns、WHS +0.107 ns。六档原始波形、50/100/200 MHz 块访问和故障不重放仿真通过。

Hazard3 80 MHz 核，128 字实际 SRAM 在 100 MHz TCK、idle 12 下读写 5.524 / 5.521 MB/s。idle 10 和 8 报 DMI BUSY。源码绑定见 [仿真证据](hazard3.json)。

HPM5301 在 100 MHz/tap16/TDO 时隙37/TMS、TDI各提前一时隙条件下，idle 32 的 1 KiB 块混合试跑 2 秒通过，读写约 3.276 / 3.424 MB/s。idle 24 及以下的读扫未通过。长测开始后 XSCT AP0 消失，用户改用 H743，本轮不再继续 HPM5301。最后一次实际 SRAM 恢复后的字节、SHA-256 与哨兵均已核对，随后调试会话清理和长窗未完成。未擦写固件。

[HPM5301 中止现场](hpm5301-interrupted.json) · [编译与上板配对](../../../../prebuilt/jtag-only-200mhz-pipeline100-20261118/manifest.json)
