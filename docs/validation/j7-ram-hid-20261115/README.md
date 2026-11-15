# J7 JTAG/RAM 镜像的 HID 连接复验

2026-11-15（上海时间），ZL-254。用户通过固定 v1.3.10 工作台的可执行手册运行 `probe-load`，默认 JTAG/RAM 加载和 OCM 核对报告通过。该路径加载的是探针本体，目标 MCU 的 Web 调试链路仍由实际配置决定。

- J7 的 USB 为 `CMSIS-DAP`，序列号 `12345678`、COM33。Windows 同时枚举了接口 3 的 HID，VID/PID `0d28:0204`、usage page `0xff00`、制造商 `CherryUSB`、产品字符串 `ZynqLink probe control`。
- 已加载配对是 `prebuilt/release-20261106/`。bit SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`，PS ELF SHA-256 `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802`。该 ELF 包含 Windows 实读的旧 HID 字符串。
- 固定 EXE 的真实本机 API 返回一只 USB 和零个 HID。当时无 USB/HID 租约及采集事务。HID 的过滤规则只允许 `zynqlinkPRO HID` 和 `CMSIS-DAP`，遗漏了同一探针旧 RAM 镜像的产品名。

修订把旧产品名加入同一制造商与 usage page 下的允许列表，本机服务、原生探针工具和验收重新枚举复用该规则。仍拒绝来自其他制造商或不同 usage page 的同 VID/PID 接口，多探针歧义规则继续生效。

用同一物理 J7、同一运行配对，在隔离源码工作台点击顶栏「连接探针」，显示 `USB + HID 就绪`。随后在「版本与构建信息」通过真实 HID 读到 `ZynqLinkPro`、序列号 `12345678`、固件 `0.6-nonce32`。断开后 USB/HID 和事务状态为空闲，原固定 EXE 会话与共享硬件服务仍在。原始记录 `build/hid-ram-descriptor-20261115/result.json`，CLI 110 项、Web 174 模块语法与共享驱动检查通过。

本轮未重载探针、未写目标 Flash、未写 QSPI，正式 QSPI `0.8-nonce32` 及既有冷启动证据沿用。此次验证针对 RAM 配对的 HID 发现与读取，不增加流吞吐或目标板验收结论。
