# SWD 可配置时序接口（仿真阶段）

这一步把第一阶段发生器的配置实际接入 SWD、RTT、HSS，并提供 vendor 0x90 和
`tools/swd_timing.py`。默认关闭扩展，继续使用 main 的波形与调频策略。
这里只做仿真、原生 C 测试和固件编译，尚未综合、加载 FPGA 或测试目标板。

[汇总与源码/固件哈希](measurements/20261027-swd-timing-configurable.json)记录了 80 项回归：
72 项正向通过、8 项明确的拒绝负例，均符合预期。另有
[180 点窗口扫描](measurements/20261027-swd-timing-windows.json)：100 MHz FCLK 的线级
模型中 60 点通过完整事务，120 点不通过；这些失败点原样保留，不计作功能通过。
真实 ARM 服务测试另使用 120 MHz FCLK，两套模型的返回延迟数值不能直接互换。

## 实际开放的能力

| 参数 | 含义 |
| --- | --- |
| FCLK | PS 实际可分频频率，设置请求是上限；范围 500 kHz～120 MHz |
| XFER_HALF_Q | 数据/请求/idle 的 Q16 半周期，1 拍编码为 65536 |
| SWJ_HALF_Q | SWJ 序列的独立 Q16 半周期 |
| ACK_HALF_Q | ACK 阶段半周期；0 表示沿用 XFER |
| TURN_HALF_Q | turnaround 阶段半周期；0 表示沿用 XFER |
| ACK_SAMPLE | ACK 独立的消费位置和输入源 |
| DATA_SAMPLE | 数据与 parity 独立的消费位置和输入源 |
| LEGACY_CFG | 原有 idle、WAIT/FAULT 数据相位、Q1/Q2、turn_extra、ACK hold 等 |

采样配置每字的格式：bits15:0 是当前捕获半相位内的零基 FCLK 偏移；bit16 为
`end`（忽略偏移，在本半相位结束处消费）；bits18:17 为输入源：0=原 CFG 选择，
1=IDDR Q1，2=IDDR Q2，3=原始输入。其余位必须为零。

**这里调的是“何时消费哪个输入样本”。** IDDR 仍连续采样；`offset` 不是从管脚
SWCLK 上升沿直接量出的纳秒延时。120 MHz 时一个 FCLK 约 8.33 ns，Q1/Q2 相差
约半个 FCLK；这次没有增加 IDELAY/ODELAY 或亚拍物理延迟单元。

采样偏移必须小于对应半周期的整数部分，确保小数分频的最短半周期也有采样事件。
位置恰好与协议事件同拍时使用当前输入；提前采样时使用已保存的 ACK/parity。
这一点避免了一拍半周期下 `offset=0` 与 `end` 本应等价却消费旧值的问题。

扩展启用后，两项旧的整数 delay 不再决定发生器周期。ACK hold 和 turn_extra
仍有效；hold 的步长随 ACK_HALF_Q 改变。独立阶段周期不表示任意组合都有物理余量。

默认一拍配置保留紧凑 ACK/连续握手。慢半周期或额外阶段拉长使用保守协议路径，
可能退回显式发起，周期成本会增加；没有宣称所有自定义配置都达到 main 同频吞吐。
main 默认设置的波形和周期不退步，另有独立基线对照。

## 寄存器：基址 0x40010000，8 位地址窗口

| 偏移 | 写入（暂存）/读取（当前生效） |
| --- | --- |
| D0 | CONTROL：bit0=扩展使能，其他位保留 |
| D4 | XFER_HALF_Q，至少 65536 |
| D8 | SWJ_HALF_Q，至少 65536 |
| DC | ACK_SAMPLE |
| E0 | DATA_SAMPLE |
| E4 | ACK_HALF_Q，0 或至少 65536 |
| E8 | TURN_HALF_Q，0 或至少 65536 |
| EC | LEGACY_CFG；读回实际 CFG |
| F0 | 命令：1=整体提交；2=丢弃暂存并复制当前配置；4=仅关闭扩展 |
| F4 | 状态：bit0=忙；bits15:8=最近硬件错误；bits31:16=提交 epoch |
| F8 | 固定能力签名 `0x53575431`，即 SWT1 |

D0～EC 支持字节写使能，暂存时可以分多次写；只有合法提交才同时改变有效配置和
legacy CFG。单核、batch、packet、HSS、RTT、待启动脉冲任一个占用时，提交/关闭
均拒绝。执行引擎 reset 保留时序配置；完整 AXI reset 才恢复缺省。

错误码：1=忙，2=CONTROL 保留位，3=半周期，4=ACK 采样，5=数据采样，
6=CFG 保留位，7=未知命令。错误提交不改变 epoch 或生效配置。

高地址已与原 0x60～0x7C 采样寄存器隔离，避免 D0 误写引擎 reset、EC 误写 HSS
地址计划。现有 BD 参数需要从 7 位更新为 8 位，构建脚本已登记，尚未执行实现验证。

## 固件和会话行为

vendor **0x90** 的输入：

- 查询：`90 00`。
- 提交：`90 01` + little-endian FCLK 请求（u32，0=不改）+ D0～EC 八个 u32。
- 关闭扩展：`90 02`。它保留当前 FCLK 和 legacy CFG，不是整套恢复出厂设置。

响应固定 44 字节：命令、DAP 状态、版本1、保留字节；实际 FCLK、硬件状态、八个
配置字。字段里的平均 SWCLK 是根据实际 FCLK/Q16 推算，不能当成逻辑分析仪实测。
固件先检查 SWT1，旧 bit 不会因高地址截断被写坏；校验或忙拒绝时不修改时钟。
FCLK 编程失败会回滚原时钟和时序配置。

启用扩展后，标准 `DAP_SWJ_Clock` 保持当前 FCLK，按请求频率计算向上取整的 Q16
半周期，保证平均频率不超过请求。ACK/TURN/SWJ 的显式覆盖及采样位置不会自动重选。
请求超过当前 FCLK/2 会报错；需要更高频率时先明确设置 FCLK。
关闭扩展后，标准命令恢复 main 的 FCLK=约2×SWCLK 策略。
旧工具若仍按 FCLK/2 显示频率，只适用于旧分频设置；扩展配置应以新接口返回的
Q16 和实际 FCLK 计算平均位频率。

RTT/HSS 接管与释放时保存/恢复整个配置，以及原 FCLK/CFG/AP 上下文。
会话借用标准时钟命令时会相应计算 Q16；采样 timer 仍按实际 FCLK 配置。
频率元数据已修正，不再一律把 FCLK/2 当成 SWCLK。

host DAP 命令会暂时暂停流服务，因此固件还检查“逻辑会话忙”：即使 PL 暂时空闲，
活动/正在停止的 RTT/HSS 会话仍拒绝改变配置。查询可以进行，响应 busy 也包含该状态。
先停止服务再配置，不在半包期间悄悄切换。

## 主机使用（以下命令没有在板上执行）

先正常连接 DAP，再检查版本并查询：

```powershell
python tools/swd_timing.py query
```

设置固定 FCLK、显式半周期和独立输入源：

```powershell
python tools/swd_timing.py apply --fclk 120000000 --half-q 65536 --swj-half-q 393216 --ack-source q1 --data-source q2 --ack-offset end --data-offset end --idle 1
```

按当前实际 FCLK 计算请求频率，或直接指定 Q16：

```powershell
python tools/swd_timing.py apply --hz 50000000
python tools/swd_timing.py apply --half-q 131072 --ack-offset 0 --data-offset 0 --ack-source q1 --data-source q1
```

`--hz` 与 `--fclk` 分两次设置，先得到实际 FCLK，避免把 PLL 量化误差隐藏进公式。
还有 `--ack-half-q`、`--turn-half-q`、`--ack-hold`、`--turn-extra`、
`--wait-data-phase`、`--legacy-phase`、`--legacy-cfg` 和 `--control 0/1`。
修改会打印读回值；失败退出码非零。查询不会重新连接、改变时序或写目标内存。

## 验证与边界

新增的 `tools/swd_timing_extended_sim.py` 覆盖：

- 完整控制器 AXI 暂存/提交、五种占用者、非法设置、地址隔离、分离 AW/W、字节写；
- 线级 SWJ、1/2/16/17 字读与16字写、WAIT/FAULT/parity、独立相位与偏移、raw 输入、Q16 和阶段周期；
- 生产 C 配置、ceil-Q16 调频、旧 bit/忙/非法参数拒绝、时钟失败回滚、上下文恢复；
- 真实 ARM MEM-AP 的兼容 profile、独立采样、提前采样、小数时钟、阶段周期；
- 新配置下 RTT/HSS 的字节/样本、跨页、环尾/环头、DMA-before-RdOff，活动 HSS
  期间真实提交被拒绝；兼容 profile 仍与原版 core 逐半拍对照。

一个确切的仿真收益：在 FCLK120 MHz、半周期2拍、外加返回延迟24 ns 时，Q1 的
周期末消费不能连接；把 ACK/数据消费提前到 offset0 后能完成真实 MEM-AP 读写和
完整 RTT/HSS。半周期约1.2拍的约50 MHz 档在选定窗口下也通过完整服务验证。
这是参数化目标模型上的结果，不能外推为当前板子已稳定支持这些设置。

`--scan` 保存整个返回窗口矩阵，包含失败点；只有选定正向回归以及明确的负例才
计算“符合预期”。小数分频、Q1/Q2/raw 及更早采样都不是对任意返回延迟的保证。

```powershell
python tools/swd_timing_extended_sim.py
python tools/swd_timing_extended_sim.py --groups csr,wire,host --scan
python tools/swd_timing_sim.py
```

结果、波形和日志保存在 `build/swd_timing_extended` 和 `build/swd_timing_sim`。
新接口会增加输入 mux 与计数逻辑，最终 Fmax、采样余量及实板吞吐仍需后续实现时序
和板级验收；本阶段没有绕过这些检查，也没有自动上板。
