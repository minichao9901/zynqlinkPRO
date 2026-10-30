# ORBTrace → PS USB 接口

本分支使用 `orbtrace_controller` 作为 PL 接收器，PS 从专用 AXI-Lite 记录 FIFO 搬运数据，
通过一个独立 bulk-in 端点交给 Web。ETM 内容是本项目接收/解帧后的字节，不是 Kingst
文件或参考项目本地桥的输出。参考上游出处见 `third_party/orbtrace/README.md`。

## PL 寄存器

基地址 `0x40030000`，32 位 AXI-Lite；AW/W 可独立握手，读响应支持反压。

| 偏移 | 名称 | 语义 |
|---|---|---|
| 0x00 | ID | 只读 `0x45544d31`（ETM1） |
| 0x04 | CONTROL | bit0 enable；bit1 清空并复位捕获；bit3:2 位宽编码 1/2/3=1/2/4 位 |
| 0x08 | STATUS | bit0 enable，bit1 曾取得同步，bit2 sticky loss/overflow，bit3 delay calibrated |
| 0x0c | LEVEL | FIFO 中可读的 16-bit 记录数 |
| 0x10 | DATA | 一次读弹出一条 `{0,source_id[6:0],byte[7:0]}`；空读返回 `0x80000000` |
| 0x14 | TOTAL | 本捕获累计入队记录数 |
| 0x18 | FCLK_REF | 设计参考时钟 120 MHz，**不是实际运行时钟** |
| 0x1c | CAPACITY | 记录 FIFO 容量，默认 4096 条 |

停止保留 FIFO 与质量状态，可继续读取；清空命令才清除它们。切换位宽需要新捕获。
外部 TRACECLK 使用 BUFIO 采样、BUFR 驱动接收逻辑，IDDR 使用 SAME_EDGE_PIPELINED
保持两个 DDR 半拍成对。没有以 false path 排除 trace 输入的 setup/hold。
四路数据先经过固定 28-tap IDELAYE2，IDELAYCTRL 使用独立 FCLK1 200 MHz 参考；
未完成校准时接收器保持复位。ELF 只配置 FCLK1 分频，不改变 PLL、CPU 或 FCLK0。
开始后若校准丢失则 sticky loss 置位。
trace 与 PS FCLK 之间通过 Gray 指针异步帧 FIFO 传递，状态两级同步。

时钟结构依据 AMD [UG472](https://www.amd.com/content/dam/xilinx/support/documents/user_guides/ug472_7Series_Clocking.pdf)
的 source-synchronous BUFIO/BUFR 用法；板级约束仍须实际线缆和目标时序验收。

## USB

VID/PID 保持 `0x0d28:0x0204`，interface 0 仍由 WinUSB/CMSIS-DAP 使用：

- EP1 IN `0x81` 与 EP2 OUT `0x02`：DAP。
- EP7 IN `0x87`：原有 J-Scope/HSS。
- **EP2 IN `0x82`：ETM 的唯一数据端点**，bulk、HS max packet 512 B。

不增加 OUT 数据端点或新的 Windows 驱动接口。已有 CDC（EP3 IN/EP4 OUT）与 HID
（接口 3，EP6）保留。Web 的共享 UsbLease 分开登记端点，禁止整设备复位破坏其它会话。

控制请求是 device/vendor IN：`bRequest=0x60, wIndex=0x4554, wLength=32`。
`wValue` 低字节：0 查询、1 开始、2 停止、3 清空；高字节在开始时提供位宽编码，四位 DDR
为 `0x0301`。控制中断只登记命令，main loop 执行捕获状态变更。

返回八个 little-endian u32：ID、状态、LEVEL、TOTAL、下一个 USB 包序号、capture ID、
实际 FCLK Hz、待处理命令。状态低三位同 PL，bit4 为 delay calibrated（bit3 留作 END），
bit31:16 为按 SLCR 和调试时钟分频器计算的实际 TCK kHz。
查询待处理命令为 0 且 enable、delay calibrated 都置位后，才可视作开始命令已应用。
另有 `bRequest=0x61, wIndex=0x4554, wLength=16` 查询四个 u32：实际参考 Hz、
FCLK1 控制寄存器、IO PLL 控制寄存器、校准就绪；Web 校验参考处于 190–210 MHz。

## ZET1 数据包

每个传输 32–512 字节，header 32 字节，最多 240 个 16-bit 记录。多字节字段均小端：

| 偏移 | u32 内容 |
|---|---|
| 0 | magic `0x3154455a`（ZET1） |
| 4 | seq，从 0 开始 |
| 8 | flags：bit0 running，bit1 synced，bit2 loss/overflow，bit3 END，bit4 calibrated，bit31:16 TCK kHz |
| 12 | count，后续 16-bit 记录数 |
| 16 | PL TOTAL |
| 20 | 实际 PS FCLK Hz |
| 24 | capture ID，重新开始时改变 |
| 28 | 协议版本 1 |
| 32… | 记录：低字节 data，高字节 source ID（bit7 必须 0） |

PS 将记录聚合到 240 条、停止或空闲 1 ms 后发布，避免每轮轮询发送极短包。
Web 使用 16 个 `transferIn(2,8192)` 预读，按提交顺序消费；解析器支持 USB 分段/合包。
停止后即使零数据也发送 END 短包，随后最多发送 16 个 ZLP 退掉剩余预读请求，
Web 等待所有请求完成；ZLP 不推进数据队列指针，也不触发整设备 reset。
发送失败保留相同队列槽
重试，只有匹配的 IN 完成事件才能归还槽；配置/复位时清除该端点旧 dTD 和完成标志。
USB reset epoch 改变时，main loop 中尚在复制的旧数据不得发布到新会话。

END 表示本次**传输**结束，不能替代匹配 ELF、同步和无丢失检查，也不代表目标所有程序
执行都已记录。overflow、seq 缺口、END 缺失、残留半包均应显示为质量问题。

## 验证入口

- `python tools/test_probe_host.py`：实际生产 C 代码与 USB/MMIO/目标 RAM mocks，包括
  EP2 IN 隔离、描述符、空结束包、失败重试、背压、复位 epoch 和原有 DAP/HSS/RTT 回归。
- `iverilog` 的 `tb_orbtrace_controller`：实际 AXI 控制器，AW/W 顺序变化、BRAM、R stall、
  空读、溢出、停止/复位，并用非零 BUFIO→BUFR 仿真时差检查 DDR 配对。
- `python tools/run_orbtrace_sim.py --rtl <CM3DbgAXI/rtl> --decoder <etm_decode.exe>`：真实
  CM3 运行代码、SWD 配置、板级接收器和 PS AXI 读取，再与原版 ORBTrace/OpenCSD 对照。
- `node --test web/tests/etm.test.mjs`：浏览器协议、文件指纹、WASM 真捕获、目标恢复等。

完整实板 trace 接收待 J7 五线实际连接后验收；不得用上述模拟证据代替上板结果。
