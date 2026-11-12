# 可执行手册验收

2026-11-12 使用独立的本机工作台会话，在真实 Chromium 浏览器按 [CLI 入门手册](../../toolbox-cli-first-run.md) 顺序点验。页面从现有 Markdown 显示 21 条命令，逐条展示输出、退出码及日志位置。固件路径和 CLI job ID 在对应步骤输入。工作台启动步骤核对当前会话。

- 主机环境、依赖校验、JTAG 预检和正式 J7 临时加载通过。bit SHA-256 为 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF 为 `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802`。物理 MEM-AP0 核对 85,844 字节 OCM 执行代码。加载后时钟寄存器计算 FCLK 为 133,333,332 Hz。
- H743 的身份读取返回 `DEV_ID=0x450`、Flash 2 MiB。原 `fw.elf` 在 SWD 10 MHz 配置下实际擦写、读回校验并复位，结果 61,208 字节和 1 个扇区。页面状态、烧录日志和原 job 查询均通过。
- 烧前与烧后各独立双读 2 MiB，整片 SHA-256 均为 `840ec9ddcc499edf5438470840b274db759c5c245a40aa177ad41f6e0946d312`，64 KiB AXI 工作区哈希一致。目标从 Flash 运行，`VTOR=0x08000000`、`DHCSR=0x01010001`、CFSR 和 HFSR 为零。
- QSPI 镜像离线核对通过，实板预检仍为 JTAG 模式。点验 QSPI 写入确认并取消。复点发现冷启动检查的固定目录会冲突，改为每次分配独立证据目录。浏览器复验显示 `BOOT_MODE=0x0`、操作提示和退出码 1。实际 QSPI 写入和冷启动留待切换拨码后复验。测试退出时采集和转发空闲，测试服务退出，共享 `hw_server` 保留。

73 项 CLI、159 项 Web 和 163 个 Web 模块语法检查通过。浏览器结果、独立读回及截图留在本机 `build/command-manual-acceptance-20261112/`。
