# 135 MHz 工作点可实现性核查

用户选择135 MHz后，在源码`ac00e7c`、tracked文件干净的状态下核查。当前板上仍是之前明确加载并测速的`prebuilt/golden`配对。只读进程检查没有发现其他板卡客户端；`hw_server`继续运行。此次没有写PLL/FCLK寄存器、暂停CPU、复位目标或加载新镜像。

**现有PS时钟树不能产生标称135 MHz。** 这不是一次135 MHz时序失败，也没有用138.461 MHz替代用户要求。精确135 MHz的产品构建/上板验收尚未执行，等待选择实际工作点或授权时钟树改造。已完成的Golden仿真、固定100 MiB源码和路由结果继续保留。

## 板上只读证据

原始XSCT读回见`live-clock-registers.txt/json`；没有发送寄存器写命令。寄存器频率按项目标称33⅓ MHz PS_REF换算，固件整数算法使用33,333,333 Hz。这里没有使用物理频率计，不能将计算值写成频率计实测。

| 来源 | CTRL读回 | 反馈倍数 | 标称PLL |
|---|---|---:|---:|
| IO | `0x00036008` | 54 | 1800 MHz |
| ARM | `0x00028008` | 40 | 1333.333333 MHz |
| DDR | `0x00020008` | 32 | 1066.666667 MHz |

`PLL_STATUS=0x0000003F`。本次快照FCLK0控制值`0x01200100`，来源IO、两级除数1和18，计算频率99,999,999 Hz；FCLK1值`0x00900100`，来源IO、除数1和9，计算频率199,999,998 Hz。现有CPU/DDR/USB控制寄存器也保存在快照中，没有变更。

UG585规定FCLK为可选IO/ARM/DDR PLL，经两个6位整数除法器输出。现有三个PLL均没有整数除数组合得到135 MHz。即使重新编程PS PLL，按标称参考：

`135 / (100/3) = 81/20`，因此反馈倍数至少81、总除数至少20，最低PLL输出为2700 MHz。DS187 Table 21规定本工程`xc7z020clg400-2`的PS PLL范围780–1800 MHz，2700 MHz超规格。`derive_clocks.py`独立枚举合法反馈倍数和1–63的两级除数，可重算`clock-feasibility.json`。

## 可以交给用户选择的方案

| 方案 | 准确标称工作点 | 需要改动 | 当前状态 |
|---|---:|---|---|
| 保留IO PLL来源 | 128.571429 MHz（1800/14） | 现有分频、配套时钟元数据/固件、正式产物与板测 | 改动最少，尚未按此点交付 |
| FCLK0切换至现有ARM PLL，或现有DDR PLL | 133.333333 MHz（ARM/10或DDR/8） | 只选择FCLK0来源，不重编程CPU/DDR PLL；固件及工具需支持按SRCSEL计算频率，并验证DAP动态调速/DDR占用 | 更接近135，但尚未实施、未上板 |
| 保持准确135 MHz | 135 MHz | 需要另加PL MMCM等时钟生成路径，重新处理业务/AXI时钟连接、复位/锁定、DAP动态调速计算及约束，重新仿真和实现 | 超出当前小范围收尾，等待用户决定 |

采用另一PLL作为FCLK0来源不会自动改变该PLL本身或CPU/DDR分频；实际修改前仍须审计所有FCLK0计算与动态切换点。当前`DAP_config.h`和板测fixture仅支持IO PLL假设，不能只改SRCSEL而保留错误频率报告。没有为了135 MHz重编程PLL，也没有把128.571或133.333标成135。

135 MHz的同路由假设STA另存于`sta/`，Vivado退出码0，约束周期7.407 ns（略严于135 MHz所需的7.407407 ns；报告时钟表因此显示135.007 MHz）。没有重新综合、布局、布线或生成bitstream。

| 检查 | 最差余量 |
|---|---:|
| 全局WNS（7 ns SWCLK输出预算路径） | +0.319 ns |
| FCLK0域setup | +0.482 ns |
| 独立200 MHz域setup | +0.363 ns |
| 全局hold | +0.033 ns |
| recovery | +0.942 ns |
| removal | +0.477 ns |
| pulse width | +0.264 ns |

TNS/THS/TPWS均为0，报告为`All user specified timing constraints are met.`。这只能回答现有逻辑在假设周期下的余量，不能证明135 MHz时钟已经产生，更不能证明135 MHz硬件通过。仍有5个双向端口缺少input/output delay；内部未约束端点、no_clock均为0。所有已知IO/CDC覆盖限制沿用`../final-evaluation.md`，没有放松真实约束，也未将工具通过宣称为所有接口已完成约束验收。

## 一手规格来源

- AMD [UG585 FPGA0_CLK_CTRL](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Register-FPGA0_CLK_CTRL-Details)：SRCSEL和DIVISOR0/1字段。
- AMD [UG585 ARM_PLL_CTRL](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Register-ARM_PLL_CTRL-Details?contentId=d84B9BHA5gXvECno3poQ1g)：PLL_FDIV为整数反馈字段，更改前需旁路/复位。
- AMD [DS187 v1.21](https://docs.amd.com/v/u/en-US/ds187-XC7Z010-XC7Z020-Data-Sheet)，Table 21（PDF第16页）：本器件-2速度等级PS PLL最高1800 MHz、最低780 MHz。

**阻塞状态：待用户选择，不是自动审批拒绝。** 精确135 MHz需要改变时钟生成架构；128.571/133.333为可审阅备选，未擅自采用。新bit/ELF、Golden同条件板测、100 MiB全区/1–2秒采集验收和产物提交仍未完成，原Golden配对保留可恢复。
