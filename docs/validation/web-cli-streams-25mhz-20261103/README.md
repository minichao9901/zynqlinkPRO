# HPM6800EVK：Web与CLI的25MHz RTT转发/HSS实测

日期：2026-11-03（Asia/Shanghai），分支`codex/web-ui-compact`，基于`996c115`。用户明确要求只测25MHz、比较Web与CLI。先核对占用；用户确认重新插拔电后加载指定探针配对。**RTT转发接近；Web HSS的连续采样稳定性明显弱于CLI，不能判本轮全通过。**

## 主要结果

这里的Web是实际冻结EXE、真实浏览器页面与本机原生USB/HID/COM通路，经公开鉴权页面API操作；不是假探针，不是只核对按钮投递，也不代表Chrome直接WebUSB的结果。原生CLI直接使用相同探针接口。最终计时期间无并行构建或其他板卡任务。

| 项目 | CLI | 最终冻结Web | 判断 |
|---|---:|---:|---|
| RTT转发，有效接收速率三轮中位 | **1.5548 MB/s** | **1.5585 MB/s** | 差约+0.24%，本轮没有明显吞吐差距 |
| HSS 1×u32，174 ticks / 7.25µs | **137.931 kS/s**，三轮稳态零跳采 | **133.068～137.931 kS/s**；跳采378/0/49172 | 峰值可相近，Web只有一轮稳态零跳采 |
| HSS 8×u32，921 ticks / 38.375µs | **26.059 k组/s**，三轮稳态零跳采 | **25.148～25.369 k组/s**；跳采6985/8877/9231 | Web三轮均跳采，损失约2.64～3.50%尝试组 |

MB/s按10^6字节；8路速率是完整变量组，不是标量总数（CLI约208.47k个u32值/s）。HSS各三轮请求10秒，按硬件24MHz tick差计算实际窗口（CLI约10.00s、Web约10.02～10.14s）；不包含启动/收尾。全会话启动跳采另保留在first/final和原始包，**“稳态零跳采”不冒充从START到STOP全程零跳采**。

最终Web进一步测试：单变量125k、111.111k、100k、50kS/s均至少一轮跳采，8路25k、23.810k、22.222k、10k组/s也未全部零跳采。因此本轮**不能给Web一个可信的固定“连续零跳采极限”**，不能拿偶尔达到137.93k/26.06k的峰值当稳定能力。低速10秒对照中，1×u32/1kS/s仍有376次稳态跳采，8×u32/1k组/s为0；说明额外停顿不限于硬件读速临界点，应单独定位（ZL-113）。

所有已成功交付的HSS原始DATA帧逐字节匹配已知RAM模式，序号、页面样本数、原始样本数及最终produced一致，尾差0，USB丢样/包缺口/读错0。**这只证明已交付数据完整，不意味着采样尝试没有跳过。**原始时间戳独立证实缺口：例如单变量174ticks第三轮raw timeline缺49174点、全会话硬件skipped=49174；1kS/s对照全会话两者均1170点（其中稳态窗口376点）。不是只看界面计数做判断。

8路界面仍出现ZL-097的span元数据警告（本地合并计划1span、探针报告8）；实际8字段值与数量完整。本轮不将该历史警告与ZL-113额外跳采预判为同一根因。

下一步优先对HSS持续USB收流、HTTP交付与主线程绘图/解析做隔离对照。源码可见当前原生HSS按HTTP请求读取512B包、单条在飞，CDC则是后台持续串口读；这提供调查方向，**尚未证明具体根因，更没有把问题归因于FPGA/目标MCU后宣称修复**。本轮不改PL/PS或为消除跳采而改变目标时钟。

## 固定条件与计时

- 测量窗口请求TCK=25,000,000Hz，物理MEM-AP0读PLL/分频得到FCLK=49,999,999Hz、TCK=24,999,999.5Hz，mode0，Web现场再读有效idle=8；CLI明确`--idle 8 --mode 0`。频率是寄存器计算，不是外部频率计测量；133.333MHz是bit约束，不是本轮运行FCLK。
- RTT使用相同RAM生产者（`firmware/target/hpm6800_usb_ram/producer.S`）、非缓存AHB16KiB环、CB=`0xf0400200`、ring=`0xf0401000`、2048B连续小端u32发布，探针块读2048B。每轮发布从0起，STOP ACK后排尾；目标发布字节、探针moved、主机文件长度精确相等，所有字节可推导，非重复hello文本判据。
- RTT每轮设5秒稳态活动段，另有启停/稳态准备/排尾；主表按首末非空接收块的活动区间计算、扣除第一块，CLI与Web相同公式，三轮中位。CLI还留独立5秒host/probe差值。Web完整8秒记录窗包含等待和排尾，不能用其约1.1～1.3MB/s的整窗平均与CLI活动吞吐混比；原始两种值全部保留。
- HSS使用相同静态AHB夹具：`random.Random(0x68004853)`的4096B模式写至`0xf0404000`，采样`0xf0404100`起1/8个u32；两边目标核心均暂停。CLI先搜索并短窗复验，再用最终无并行构建的三轮10秒复测174/921ticks；Web同条件测试这两个点及更慢对照。CLI/源码Web的早期短窗与中间长窗也归档，不替代最终冻结结果。
- Web显示、解码、原始包记录开启；数据端点本机native路径64KiB/单在飞，CLI HssReader为32KiB连续读。保留真实产品路径的区别，不把Web换成脱离界面的CLI读线程来制造相等。两边读取同一AHB位置、目标寄存器控制/缓存状态保持不变；未写目标PLL/AHB/APB。

## 为真实25MHz补齐Web能力（ZL-111）

前一版本的Web RTT转发/HSS沿用旧软件探针协议：RISC-V字段发0，目标类型确认后Zynq默认10MHz。直接按它测速会错误地把10MHz当成25MHz。现在识别`model=ZynqLinkPro`后，两页开放10/20/25MHz JTAG TCK；启动时先确认架构，再下发所选Hz并检查ACK。原软件探针/未知型号仍保持0/idle约定，不发送错误Hz；HPM上限仍25MHz。

为RTT记录增加首末数据到达时间和有效接收速率字段，原始数据和原整窗计时不变。RTT时钟字段正确标为JTAG TCK，配置拒绝不再显示成功。ARM、其他探针未做本轮硬件验收。

固件HID状态只给整数MHz，本轮`actual_hz/1e6`向下取整会显示24；请求25和实际24,999,999.5Hz必须与这个低精度字段区分（ZL-112，待修复）。主表以物理时钟证据为准，没有把24显示当作真实降频。

## 失败、对照与脚本修正

1. 初始未检测到业务USB，PL/AP0读超时。用户确认重新插拔电后，JTAG启动模式boot_mode=0，DAP报30000021、无APU。选DAP系统复位后恢复APU；普通加载脚本在ps7 DDR初始化被SDK blocked-address保护拒绝。按配套标准ps7初始化明确设置force-mem-access后，完整RAM加载成功，物理OCM匹配76420B。日志全部保存，未写QSPI；这是未初始化探针的准备阶段，不能冒称已经运行配对的USB故障复现，也不能据此关闭历史ZL-060。
2. 源码Web HSS首次START=-7、0包：测试RAM夹具保留了DAP连接/IR状态。夹具写完明确DAP_Disconnect后再交Web；未重载bit/ELF、未复位目标掩盖失败。原失败`web-hss.json`保留。
3. Web整数µs周期使用v1（例如40µs），小数周期使用v2 ticks。首个冻结960ticks窗口被仅支持v2的旧验收读取器错误拒绝；原结果与原始包保留。新验收器只统一头部时间戳单位，保留原始文件且不改变值载荷，继续检查完整序号/时间线/所有值。该窗口离线重验292244点、尾差0、硬件跳采4686，见`v1-revalidation.json`。补充2项格式测试，包含坏值、序号缺口及未知版本仍须失败。与ZL-090的验证工具契约问题一起记录，不归为产品USB损坏。
4. Web所有高/低速失败轮保留，不以复测偶尔0跳采销案。原始包留本机build，`raw-evidence-manifest.json`归档54个文件的SHA、点数、逐帧值校验及时间戳缺口；大批可再生测试数据不重复提交Git。RAM/GPR备份只留私有build目录。

## 验证、配对与最终状态

`web.check`：159个模块、10份共享驱动一致；123项Web自测通过；HSS v1/v2独立解析2项通过。冻结EXE自身无Python/Node环境预检/离线Trace验收通过。最终冻结程序的实际RTT三轮和上述HSS各窗口验证是硬件证据，**不能因主机测试通过而宣称HSS稳定性通过**。

4个变更/新增产品资源与最终冻结包逐字节一致，SHA见`source-package-binding.json`；manifest如实记录baseRevision=`996c115`、sourceDirty=true。最终程序仍在独立`dist/zynq-etm-bridge-candidate-20261103/`；没有更新其他工作区程序、没有推送或合并main。

实际RAM加载的既有配对：`prebuilt/hpm6800-usb-fixed-133-20261102/`。

- bit SHA-256：`106d579bc1b79c2b873fd1e3eb2609d468892a67613d85a6e41d4dc90c8fc177`
- Zynq ELF SHA-256：`e93f1810d48e77f8d9aa097f643e40e0aaee32bdec1c263c1428f092909e608a`
- 加载后和最终物理MEM-AP0核对76420个可执行字节匹配，未修改RTL/PS或生成新配对。

外层RAM夹具备份并最终逐字节恢复ILM256B、AHB32KiB；完整GPR/DPC/mstatus及DCSR可写位核对、缓存控制和目标时钟寄存器核对通过。原程序已继续运行，最终DMSTATUS=`0x430ca2`；不是重刷/复位目标后冒充恢复。探针最后设回本任务25MHz档，TCK=24,999,999.5Hz、FCLK=49,999,999Hz、mode0、idle8，DAP连接已释放。RTT/HSS及物理采集/DDR/CDMA/packet引擎均空闲，见`fixture-restore.json`/`final-state.json`/`final-ocm.json`。未写目标Flash或探针QSPI。

本任务浏览器、源码服务、冻结EXE、测试线程均已关闭；共享hw_server保留。所有“最终状态”只代表该时点，掉电/换工作区不会自动加载这对产物。

## 复测入口

先按AGENTS核对占用、加载配对、物理OCM及目标状态；`--elf`在原生stream工具中是探针PS ELF，在Web工具中是目标ELF，不混淆。

```powershell
# 下列帮助/计划不操作硬件；实际运行需用户允许，并使用全新的输出/fixture目录。
python -X utf8 toolbox.py project describe tools/validate_hpm6800_streams.py
python -X utf8 tools/benchmark_web_cli_25.py --help
python -X utf8 tools/benchmark_web_cli_25.py --stage web-hss --fixture build/fixture-new --out build/comparison-new
```

`tools/hpm6800_usb_fixture.py install/restore`负责权威RAM/寄存器备份；新对照工具的`prepare-rtt/prepare-hss`仅在已安装的同一外层夹具内使用。Web需保持鉴权浏览器worker运行，方法先describe发现；工具显式`--execute`才访问硬件，文件夹规划成功不是实板验收。
