# 133.333 MHz 收尾验收

用户已同意133.333 MHz替代原先无法直接分频得到的135 MHz。**本次配对已完成F103范围验收并最后重新加载、核对身份。** 实际使用的[bit/ELF及manifest](../../../../prebuilt/fclk133-release-20261101/README.md)均为本次新生成，原Golden没有覆盖，也没有写QSPI或目标Flash。

采用现有ARM PLL（反馈40）给FCLK0分频10，标称133⅓ MHz；项目按33,333,333 Hz参考计算的读回频率为133,333,332 Hz。不会重新编程PLL，也不修改CPU/DDR/USB分频或独立200 MHz FCLK1。普通DAP调速保留原IO PLL策略，25/60 MHz链路与Golden比较时使用原有档位；133.333 MHz为启动及明确选择的离线DDR录制工作点。

133.333 MHz与外部60 MHz不能用同一个FCLK整数半周期同时精确实现。DDR录制验收使用已记录的较低SWD控制速率；正常SRAM/RTT/HSS的60 MHz对照仍保持FCLK约120 MHz，不会将内部提频当作链路性能提升。

冻结RTL来源`e749c42`的24个文件哈希全部匹配现有布线，复用路由DCP，仅重做133.333 MHz完整STA并重新生成bitstream。固件来源支持为`0118b16`，桌面固件7组服务回归和10项Python时钟/内存检查通过。之前同条件Golden/候选RTL仿真十项有效吞吐指标完全一致，见`../final-simulation/`。

固定DDR尾100 MiB：`0x39C00000..0x40000000`（end exclusive）。采集时间到或写满后停止接收、排空在途数据并报告准确有效长度。诊断区已移到`0x39000000`，固件堆/栈、USB/staging/描述符不与录制区重叠；链接和实际读回检查均通过。配套ELF的OCM占用120,976字节，余140,656字节。

## 时序与资源

133.333 MHz周期7.500 ns；独立参考周期5.000 ns。新bitgen的DRC为0错误、46警告；`RTL_DEBUG=0`、可选观察寄存器为0。当前资源18,210 LUT、21,148寄存器、40.5 BRAM tile、1 DSP。此前同模块debug on/off综合对比节省3,376 LUT和9,673寄存器，详见`../debug-audit/`，这不是另一份正式业务镜像。

| 检查 | 最差余量 |
|---|---:|
| FCLK0 setup | +0.575 ns |
| 全局WNS（7 ns SWCLK输出预算） | +0.319 ns |
| hold | +0.033 ns |
| recovery / removal | +0.942 / +0.477 ns |
| pulse width | +0.264 ns |
| 独立200 MHz域setup | +0.363 ns |
| SWDIO Q2 / TDO Q2 | +0.586 / +0.680 ns |

setup/hold/recovery/removal/pulse-width已定义检查全部通过，TNS/THS/TPWS为0。各路径族、两采样相位、异常约束、CDC及原始控制台均在`sta/`，未以放松7 ns预算、添加false path或新一轮布局来取得通过。

**覆盖边界：**5个双向GPIO/SWDIO端口仍缺外部input/output delay，内部未约束端点和no_clock为0。CDC仍有35项CDC-1、8项CDC-7、4项CDC-10及9项CDC-6/548项CDC-15；含Gray同步、握手保持总线和复位结构。本记录不声称所有接口完成正式CDC/IO签核。`verified_clock.json`保留bitgen阶段的`formal_product_acceptance=false`；配对最终板测结论独立记录在`validation.json`。

## Golden同条件性能

RTL Golden/候选在同一模型、时钟、事务规模下的十项payload/周期指标完全一致，证据在`../final-simulation/`。本次硬件SRAM使用相同512字/depth32/256循环、三次重复及10秒交替读写；RTT使用1024字节块、三次2秒窗口，字节/序列、RAM/寄存器/时钟恢复均检查。

| 指标 | Golden | 本次 |
|---|---:|---:|
| SWD60 SRAM读/写 MB/s | 4.830683 / 4.745757 | 4.835004 / 4.746595 |
| JTAG60 SRAM读/写 MB/s | 2.421895 / 2.397811 | 2.421693 / 2.398331 |
| SWD60 RTT MB/s，目标ETM暂停 | 4.647699 | 4.647907 |
| JTAG25 RTT MB/s | 0.976324 | 0.973788 |
| SWD60 HSS零跳采上限 | 1 MHz，24 ticks | 相同，三次零跳采 |
| JTAG60 HSS零跳采上限 | 324,324 Hz，74 ticks | 相同，三次零跳采 |

SRAM/RTT速率为有效payload的重复测量中位数，未观察到可区分的下降。JTAG25 RTT的Golden三次范围0.972220–0.977313 MB/s，本次0.973781–0.977472 MB/s；不能将中位数的小波动当作确定性能差异。SWD RTT使用本次重新加载并核对身份的Golden隔离对照，其余Golden来源为`../board-golden/`。

**RTT现场条件与失败保留：**首次新配对SWD60 RTT失败，重新加载的Golden也失败。改用AP0或移出运行窗口的时钟观察均未解决，相关失败JSON保留在`board/rtt-ab/`。只读检查发现目标`ETMCR=0x810`仍在输出；暂置编程态`0xC10`、保持60 MHz和原目标时钟后，原Golden与新配对各三次均通过，全部发布字节收齐、序列准确、错误0，并恢复`0x810`及锁/运行状态。触发机制尚未定位；**并行ETM输出与60 MHz RTT不在本次通过范围**。隔离脚本和原始结果在`board/rtt-isolated/`及`board/drivers/`。原Golden60 MHz JTAG RTT失败与本次对应失败均保留，25 MHz JTAG RTT才作为有效比较。

## DDR和真实ETM

| 验收 | 结果 |
|---|---|
| 全区模式写入/物理读回 | 104,857,600字节全部匹配，SHA-256 `183c495d9da1353d0fd21e4a49502669ae33f865c095fab6e2bc308fecc17bfa`，边界哨兵不变 |
| 1秒，入口cdc_poll | 19,859,026字节，硬件窗口内61次准确CDC回显 |
| 2秒，入口cdc_tx_poll | 39,782,064字节，硬件窗口内125次准确CDC回显 |
| 100 MiB写满停止 | 104,857,600字节，5.278425673秒，stopReason=2、capacityReached=true、tailBytes=0、边界哨兵不变 |

1/2秒期间不读取探针USB数据端点，只做必要控制；采集完成后再USB下载，并与同一DDR记录的物理MEM-AP0哈希比对。丢帧、解析错误、IDELAY参考失锁、writer错误均为0。两次完整解码分别检查约478万/958万个包和1,956万/3,918万个执行范围，内部坏包、不同步字节、不可达地址均为0。目标Flash按原CDC48 ELF逐段核对，没有重刷或改目标时钟。

真实ETM在2秒内不足以填满100 MiB，因此写满测试只在物理硬件验收入口设置12秒等待上限，实际提前因满结束。产品USB接口仍限制最多2秒，越界测试入口保护已验证；不把该物理边界测试称为产品12秒能力。

最初ARM133/33.333 MHz控制波形在CPUID读取时失败，尚未开始采集；原始记录在`board/etm-window/`。最终使用经32次只读CPUID验证的标准SWD约995.025 kHz，ARM133验收fixture现限制控制速率不超过1 MHz，已通过的1/2秒和满测试都用此波形。采集中普通DAP25 MHz调速命令被拒绝，FCLK和CFG不变；结束后原控制配置恢复。

## 时钟与产物身份

FCLK0来源/分频读回、固件vendor频率返回一致为133,333,332 Hz；原ARM PLL反馈40、IO反馈54、DDR反馈32和CPU/DDR/USB/FCLK1控制配置不变。1秒和2秒的主域计数为133,333,545和266,666,869，参考计数为199,999,998和399,999,996；差分约133,333,324周期/秒，与分频计算相符，少量差异包含启动/排空记账。绝对频率没有用外部频率计校准，仍以板上PS_REF为基准。

- 实际加载bit SHA-256：`af1031d3caa0d7bd3b6adffa911d26efdab9e0bfb5223fb18f70dabb70ebeeed`
- 实际加载ELF SHA-256：`2137f7d0f507c08574f36223130103c0710645cbfdefb5c1d8c8efb0cfb990a0`
- 保留的输入路由DCP SHA-256：`aa3897d8b421ec15431b7b56762376b313030bc3f2a05121bb70b49753112916`

`board/final-load/`保存最后一次实际加载及独立OCM代码匹配证据；`ps/`为本次编译和链接布局，`tests/`为固件服务/时钟与边界入口回归。大体积原始DDR/ETM及展开的native数据仍保留在本地`build/fclk-resume-20261101/board-133/`，Git中保留其哈希、完整检查结果和复测驱动。未继续150/160 MHz探索，未制作双业务镜像、未更改QSPI。
