> 仓库内归档：本目录现包含CB/ZE目标所需CMSIS/HAL、CherryUSB、RTT、链接脚本、构建封装及host测试，无需原build/worktree。
> 主要验收入口与固件身份见[统一文档](../../../docs/F103ZE-Web-CLI-ETM统一验收-20261031.md)。
> 离线构建：`pwsh -NoProfile -File firmware/target/stm32f103_cdc_trace/build.ps1 -Chip ze -CpuMHz 48`，72MHz显式指定`-CpuMHz 72`。
> 主机回归：`pwsh -NoProfile -File firmware/target/stm32f103_cdc_trace/tests/run_tests.ps1`（本机gcc）。
> 本目录编译不连接板卡。硬件烧录优先使用统一toolbox CLI，遵守双方设备独占交接。
> 下文保留上游README；其旧工作区路径、下载链接和直接烧录示例不是本轮可盲目执行的验收步骤。

# STM32F103 + CherryUSB CDC ACM（etm-trace 目标固件）

> **状态：已在线验证通过（2026-10-12）**
> 板子：F103CB/R8（64K/20K），探针 akaLinkPro CMSIS-DAP。
> 枚举结果：`USB\VID_F055&PID_1031\F103CDC0001` → **COM33**；CDC 自检 **6/6 通过**
> （PING/INFO/MARK/ECHO/未知命令/原始回环）；`INFO` 返回 `sysclk=72000000Hz clk_err=0`。
> 注：首次插上若 Windows 里有旧的坏节点（`VID_0000&PID_0002`），先在设备管理器卸载它再插拔一次。


## F103ZE 当前默认档（2026-10-13）

`build.ps1 -Chip ze` 现在生成 **CPU/HCLK 48 MHz、引脚 TRACECLK 24 MHz** 的 `fw-ze.elf/.bin/.hex`；
USB 时钟仍为 48 MHz（PLL 直接供 USB，Flash 1 等待周期）。CB 默认 72 MHz 不变。
显式对照档 `build.ps1 -Chip ze -CpuMHz 72` 生成 `fw-ze-72.*`，不会覆盖默认 48 MHz 固件。
显式 `-CpuMHz 48 -TraceWorkload` 继续生成 `fw-ze-48-workload.*`。

本例普通固件不自行开启 ETM。网页负责 ETM/TPIU，**分支广播默认关闭**。
相同 CDC 初始化起点、500 MSa/s、10 ms 实测：原 72/36 MHz + 广播开为 63 次 overflow；
48/24 MHz + 广播开为 16 次；48/24 MHz + 广播关连续三轮均为 0。
仅降频不足以保证无 overflow，业务负载和 Trace 选项同样影响输出量。
详见 [F103ZE-CDC-48MHz与ETM选项验收](../../docs/F103ZE-CDC-48MHz与ETM选项验收.md)。

**基底**：你提供的参考工程 `cherry_drag_n_drop_bootloader_fat16`（MSC 拖拽 IAP，已在同一块板验证可枚举）。
本工程**只做三处改动**，USB 底层一行没动：

| 改动 | 内容 |
|---|---|
| ① USB 类 | `class/msc` → `class/cdc`，用 CherryUSB `demo/cdc_acm_template.c` 改写（详见 `src/main.c` 文件头） |
| ② 删减 | 删掉 `flash_fat16.c/.h`、`flash_intf.c`、`msc_ram_template.c`、DFU/IAP 跳转、`App.bin` 相关 |
| ③ 增加 | etm-trace 钩子（SEGGER RTT 日志 + DWT 打点 + 固定地址诊断变量） |

保留原样的部分：`cherryusb/core`、`cherryusb/port/fsdev`（含 `usb_glue_st.c`）、`cherryusb/common`、
`sdk/Drivers`（CMSIS + STM32F1xx_HAL_Driver）、`sdk/stm32f1xx_hal_conf.h`、
`src/stm32f1xx_hal_msp.c`（**含关键的 `HAL_PCD_MspInit`**）、`src/stm32f1xx_it.c`、`src/system_stm32f1xx.c`。

CDC 类文件来自 CherryUSB v1.6.1 的 `class/cdc/`（v1.5.2 里没有 CDC 类；`usbd_cdc_acm.c` 只用
`usbd_ep_start_write/read`、`usbd_get_ep_mps` 这几个 API，在 v1.5.2 的 core 上原样可用）。

---

## 1. 构建 / 烧录

```powershell
pwsh -NoProfile -File .\build.ps1              # 在线板 F103CB/R8（64K Flash / 20K RAM）
pwsh -NoProfile -File .\build.ps1 -Chip ze     # F103ZE，默认 48/24 MHz，输出 fw-ze.*
pwsh -NoProfile -File .\flash.ps1              # pyocd 烧录（换 -Chip ze）
```

启动文件的 USB 向量补丁已随工程保留；如重新导入原始 SDK，请先运行 `tools\prep.ps1`（幂等）。`build.ps1` 不自动执行该准备脚本，构建后会自检 USB 向量。

实测占用：`text 19292 + data 140 = 19432` 字节 Flash，`bss 5372` 字节 RAM（F103CB 够用）。

## 2. 目录

```
stm32f103_cdc_trace/
├── build.ps1 / flash.ps1
├── ld/stm32f103cb.ld        # 64K/20K
├── ld/stm32f103ze.ld        # 512K/64K
├── src/
│   ├── main.c               # ★ 唯一需要看的应用文件：时钟/GPIO/UART + CDC ACM + 命令行
│   ├── stm32f1xx_hal_msp.c  # ★ 关键：HAL_PCD_MspInit（开 USB 时钟 + 使能 HP/LP 两条中断）
│   ├── stm32f1xx_it.c       # SysTick + USB_HP_CAN1_TX_IRQHandler（补 glue 缺的那条）
│   ├── system_stm32f1xx.c   # ST 原版（不配 PLL，时钟由 main 里的 SystemClock_Config 配）
│   ├── trace_hooks.c/.h     # etm-trace 钩子（RTT + DWT + 固定地址诊断结构体）
│   ├── syscalls.c           # newlib 最小桩
│   ├── main.h / stm32f1xx_it.h
├── sdk/Drivers/…            # CMSIS + HAL（照搬参考工程）
├── sdk/stm32f1xx_hal_conf.h # 照搬参考工程（含 HAL_PCD_MODULE_ENABLED）
├── segger_rtt/              # SEGGER RTT（日志通道，不需要 SWO 引脚）
├── cherryusb/{core,class/cdc,common,port/fsdev,config}
└── tools/
    ├── prep.ps1             # ★ 构建前必跑：解开 ST 启动文件的 USB 中断弱别名锁定
    ├── fault_dump.py        # 抓 HardFault 现场（栈帧 + CFSR/HFSR）
    └── min_probe.py         # pyocd 读内存（比 pyocd cmd 可靠）
```

## 3. ★ 唯一的移植障碍：GNU ld 下的"弱别名锁定"

ST 的 `startup_stm32f103xb.s` 对每个中断都写了：

```asm
.weak      USB_LP_CAN1_RX0_IRQHandler
.thumb_set USB_LP_CAN1_RX0_IRQHandler, Default_Handler
```

**实测（arm-none-eabi-gcc 10.3.1 + GNU ld）**：

| startup 里的写法 | `nm startup.o` | 向量表指向 |
|---|---|---|
| `.weak` + `.thumb_set` 都在（ST 原样） | `W`（弱定义） | `Default_Handler`，我们的强定义**不生效** |
| 只留 `.weak` | `U`（未定义弱符号） | **仍** `Default_Handler`（未定义弱符号也赢过强定义） |
| **两条都去掉** | `U`（普通未定义） | **正确解析到我们的强定义** ✓ |

调整链接顺序、`--defsym=名字=名字`、`--defsym=名字=新名字` —— **全部无效**。

**对照**：你 MDK 编出来的 bootloader axf 里是
`0800011a W USB_HP_CAN1_TX_IRQHandler` / `080018dc T USB_LP_CAN1_RX0_IRQHandler`
—— ARM linker 会把启动文件里 `.word` 的未定义引用解析到强定义，所以 MDK 下一切正常。GCC 这条链不一样。

**不处理的后果**：USB 中断永远进不来 → F1 枚举卡在"取设备描述符" → Windows 报
`未知 USB 设备(设备描述符请求失败) Code 43`。这正是我一开始踩的坑。

`tools/prep.ps1` 就是干这件事：把这两个中断的 `.weak` / `.thumb_set` 删掉（原文件备份为 `*.s.orig`）。
`build.ps1` 里的自检会读向量表，确认两个 USB 向量**不等于** `Default_Handler` 的地址。

### 第二个小坑：glue 缺 `USB_HP_CAN1_TX_IRQHandler`

CherryUSB 的 `port/fsdev/usb_glue_st.c` 在 F1 上定义了 `USB_IRQHandler` 与 `USB_LP_IRQHandler`。
但 F1 头文件里 `USB_LP_IRQHandler` 只是**宏别名**（→ `USB_LP_CAN1_RX0_IRQHandler`），
所以 LP 那条向量能直接对上；而 **`USB_HP_CAN1_TX_IRQHandler` 没有任何别名**，glue 也没定义它 ——
把弱别名解开后就会暴露 `undefined reference to 'USB_HP_CAN1_TX_IRQHandler'`。
本工程在 `src/stm32f1xx_it.c` 里补了这一条（转调 `USBD_IRQHandler(0)`，与 LP 完全一致）。

## 4. CDC 命令

`PING` / `INFO` / `MARK` / `ECHO on|off` / `ECHO <text>`；默认"收到什么回什么"。
`INFO` 会返回 `usbirq / ctr / rst / err / susp` —— 排查枚举问题最有用的一组证据。

测试：`python ..\tools\cdc_test.py --list` 然后 `--port COMx`。

### 已知取舍：连发时会丢字节（不是 USB 故障）

`cdc_write()` 在 `ep_tx_busy_flag` 置位时**直接丢弃**这一条，不阻塞主循环 —— 这是刻意选的
（裸机主循环不能被 USB 拖死）。因此 `cdc_test.py --speed` 这种"主机狂发、要求逐字回环"的测试
会看到丢字节（实测发 8KB 回来 5KB）。

- 命令行交互（PING / INFO / MARK / ECHO）**完全正常** —— 每次只有一条小消息，不会撞上 busy。
- 要做到**无损高速回环**：改成"环形缓冲 + 在 IN 完成回调里续发"，而不是 busy 就丢。
  `usb_dc_ep_write` 在端点 NAK 时返回 `-USB_ERR_NAK`，可在那里挂起重试。
  全速 USB CDC 的实际上限约 **1.2 MB/s**（12Mbps 扣协议开销）。

## 5. 运行验证（不需要 USB 主机）

| 地址（F103CB） | 内容 | 期望 |
|---|---|---|
| `0x20004000` | `g_trace`（56 字节） | `31524354`（`'TRC1'`）、`sysclk=72000000`、`ready=1` |
| `0x20003000` | `_SEGGER_RTT` | `"SEGGER RTT"` |

```powershell
python .\tools\min_probe.py --target stm32f103cb --read 0x20004000:56 --read 0x20003000:12
python .\tools\fault_dump.py --target stm32f103cb     # 跑飞时定位故障指令
```

⚠️ 用 SWD 读内存前先 `halt`；**不要**在读 RAM 的同时让 CPU 跑（会读到撕裂数据）。
另外：固定段，**长时间 halt 之后再 resume 时
调试器可能把栈帧压进这个区域**，导致 `g_trace.magic` 读出来不是 `'TRC1'`。
判断"固件是否真的跑起来"更稳的办法是看 `USB->CNTR`（应为 `0xBD0C`）和 `RCC->APB1ENR` 的 USBEN 位。

## 6. 硬件与时钟

| 项 | 值 |
|---|---|
| HSE | 8 MHz（`HSE_VALUE=8000000`） |
| SYSCLK | ZE 默认 48 MHz（PLL ×6）；CB / ZE 对照档 72 MHz（PLL ×9） |
| USB 时钟 | 恒为 48 MHz：48 MHz 档 PLL /1，72 MHz 档 PLL /1.5 |
| USB 引脚 | PA11=DM，PA12=DP，全速，内部 1.5k 上拉 |
| 打点脚 | PA1（`trace_hook_mark` 翻转）；PA0 保留给参考工程原有的输入用途 |

## 7. F103 的 trace 能力（按型号分档，别搞混）

| 型号 | Flash | ETM | 依据 |
|---|---|---|---|
| F103C4/C6 | 16–32K | ❌ | DS5319 无 ETM |
| **F103CB/RB/C8（在线板）** | 64–128K | ❌ **无** | DS5319 Rev 20 Features 只写 SWD + JTAG |
| **F103ZE/xE（目标板）** | 256–512K | ✅ **有 ETMv3** | DS5792 Rev 13 Features：`Cortex-M3 Embedded Trace Macrocell`；RM0008 §31.1 |

RM0008 §31.15.1 结论：**DWT/ITM 管数据跟踪，指令流跟踪必须靠 ETM**。
所以当前这块 CB 板做不了指令流 trace；ZE 版用 `-Chip ze` 构建。ZE 固件在
`MX_GPIO_Init()` 中启用 GPIOE 时钟，并将 PE2（TRACECLK）、PE3～PE6（TRACED0～3）
设为 50 MHz 复用推挽输出。ETM/TPIU/DBGMCU 的使能和 Trace 参数仍由上位机通过
SWD 配置。RTT 日志在两种板上都能用（不需要 SWO 引脚）。

2026-10-13 的 PXLogic 对照实验：未初始化 GPIOE 时，PE3/PE4 上大多是 1～3 ns
低脉冲，PE5 几乎恒高，无法按 36 MHz DDR Trace 解码；临时经 SWD 启用 GPIOE
并将 PE2～PE6 设为复用推挽后，四条数据线均有持续活动。此处的固件初始化
用于修复该引脚配置缺失；完整执行流解码仍需单独验收。
