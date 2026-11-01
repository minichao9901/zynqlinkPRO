# ELD1逐线输入延迟实验

本阶段为RAW4实际输入端增加5个IDELAYE2：D0、D1、D2、D3、TRACECLK各自0～31 tap。默认旁路保留原输入路径；启用后，延迟输出实际进入200MHz同步器与稳定两点滤波，再进入formatter/DDR。它仍是过采样接收器，不是新增的源同步IDDR接收模式，不能据此承诺超过过采样结构的频率上限。

构建须同时设置`ZYNQLINK_RAW_TRACE=4`、`ZYNQLINK_ETM_DDR=1`、`ZYNQLINK_ETM_LANE_DELAY=1`。时钟STA选项沿用`ZYNQLINK_IMPLEMENT_FCLK_HZ=120000000`。默认生产构建不启用新参数；旧Golden与当前已知可用配对不变。新bit/ELF须另行生成、明确加载和验收，仿真不能替代。

## 配置事务

AXI时钟域保持一个26-bit配置载荷直到200MHz参考域确认；该参考域显式LD装载全部tap，等待CNTVALUEOUT更新并核对，之后才发布确认。配置忙或读回失败时，两条采集入口均不ready；独立参考时钟使目标TRACECLK停止时仍能装载。capture prepare重置IDELAYCTRL校准时，已选tap不变，采集等待RDY恢复。失败不重放命令，空闲时可显式重新装载。

| Zynq物理地址 | 含义 |
|---|---|
| 0x40030048 bit9 | ELD1存在；bit8仍为DDR CSR存在 |
| 0x40030050 | 签名0x454c4431 |
| 0x40030054 | 读：已提交配置；写：一次带key的配置事务 |
| 0x40030058 | bit0启用、bit1忙、bit2 ready、bit3已LD核对、bit4装载故障、bit5拒绝粘滞标记 |
| 0x4003005c | 已接受命令数 |
| 0x40030060 | 拒绝数 |
| 0x40030064 | 装载/读回失败数 |

配置字：bits31:26必须为0x2d；bit25为启用；bits24:20为CLK，bits19:15为D3，bits14:10为D2，bits9:5为D1，bits4:0为D0。必须完整WSTRB=0xf。legacy采集、DDR持有/准备、FIFO非空、校准未就绪或已有事务时，不改任何tap；非法key/部分写同样拒绝并计数。拒绝记录保留，不能用静默重试抹去。

AI CLI通过物理MEM-AP0访问寄存器，不改target时钟或Flash；它先检查ELD1及DDR存在、两条采集均空闲，再只写一次，并在同一XSCT事务内检查确认、计数、读回值。例：

```powershell
python toolbox.py project run etm.lane-delay -- status --out build/lane-status-new
python toolbox.py project run etm.lane-delay -- set --enabled 1 --taps 0,8,16,24,31 --out build/lane-set-new
python toolbox.py project run etm.lane-delay-sim -- --out build/lane-simulation-new
```

## 仿真与后续硬件门槛

功能模型覆盖独立延迟时间、停止TRACECLK仍可装载、非法key/部分写/忙/有效采集中拒绝、强制CNTVALUEOUT错误、LD过程中RDY丢失、显式恢复、capture prepare不改tap。带0.2/0.8/1.4/2ns逐线偏斜的相同36MHz量级数字输入，旁路无法恢复正确帧，调节后16帧完全匹配；1ns脉冲不被RAW4当成有效边沿。旁路和启用延迟各执行原9项pins→DDR窗口/容量/EOF/错误响应检查。

这不是模拟电气、亚稳态或零BER证明。当前没有完成自动选窗算法、真实杜邦线tap扫描、36MHz稳定性或H743验收。上板需先核对新配对身份及5个真实VAR_LOAD原语，验证旁路24MHz基线，再对SRAM72MHz target的36MHz首错基线做同条件扫描；记录所有失败点，保留原始数据。选择候选后再做原生解码和CDC/Web压力，不凭短窗无parser错误宣布成功。

硬件依据：[AMD UG471，输入延迟及VAR_LOAD控制，第116～123页](https://docs.amd.com/api/khub/documents/IbGcnPFe6eF19RHma_Y~IA/content)。VAR_LOAD须显式LD及读回，不能用IDELAY_VALUE当作加载已完成；IDELAYCTRL参考校准也不等于从实际数据测得采样窗口。
