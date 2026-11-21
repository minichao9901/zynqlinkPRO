# F103ZE SRAM ETM 对照程序

`fw.elf` 是目标 Cortex-M3 的 SRAM 工作负载。它提供 F103 额定范围内的 72 MHz HCLK、36 MHz TRACECLK 实验档，保留符号、DWARF、异常向量及独立的 RAM 加载段。本轮已验证构建、异常向量与 SRAM 加载计划，物理采集待验证。

从源版本 `eeb4c2d9` 的 `firmware/target/stm32f103_cdc_trace`，使用 GNU Arm 10.3.1 构建。

```powershell
pwsh -NoProfile -File firmware/target/stm32f103_cdc_trace/build.ps1 -Chip ze -CpuMHz 72 -Ram -TraceWorkload
Get-FileHash prebuilt/targets/f103ze-sram-etm72/fw.elf -Algorithm SHA256
```

归档文件 SHA-256 为 `7d19bf7690725a03c14ae0802628032ec0cdc5de842d2a1be07d6520d9952056`。原生采集参数 `--ram-image --elf prebuilt/targets/f103ze-sram-etm72/fw.elf` 校验已运行镜像的加载字节与 VTOR。加载和启动由单独的 SRAM 夹具负责。
