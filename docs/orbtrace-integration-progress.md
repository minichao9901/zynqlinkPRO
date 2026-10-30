# ORBTrace / ZynqDAP 集成进行中

目标：提交代码与本次 bit/ELF；J7 相邻五脚接 trace；单 bulk-in 接 PS USB；本仓库纯 Web
保留串口、终端、RTT 转发、J-Scope、烧录器、调试器、ETM、工程生成；产出 bit 并报告资源。
本文件是工作记录，不能作为交付或上板验收结论。

## 2026-10-30 08:08 后更新（以下旧进度保留供排查）

- `orbtrace_native32_idelay_build.log` 构建成功并实际生成 bit。trace 四路固定 IDELAY 与
  200 MHz 校准参考已纳入板级实现，4 IDDR / BUFIO / BUFR 和零 latch 检查通过。
- 修正 AXI advanced options，使五个内部 crossbar 实际为 32 位；实现后 19,228 LUT、
  27,858 FF、10 BRAM、1 DSP。LUT 比旧候选减少 5,191，细节见 `orbtrace-area-native32.md`。
- 当前测试档位中 FCLK 100 MHz 通过 setup +0.568 / hold +0.024 ns，120 MHz setup 失败。
  ELF 已按 50 MHz SWCLK/TCK 上限重新编译，实验配对保存在
  `prebuilt/20261030_orbtrace_native32/`，尚未加载实板；已知可用配对保留。
- 最终 IDELAY 功能仿真的 CM3 100 MHz / TRACECLK 50 MHz 捕获为 **1948 字节、276 帧、
  22036 指令范围**；160 MHz 压力用例仍为 3126 字节、443 帧、35360 范围。
  当前仿真源码哈希与 acceptance 一致，Web 样例已同步到最终捕获。
- 生产 C mocks 五组测试、127 个 Web 模块检查与七组 Web 测试通过。
- 剩余：native-32 实板 DAP/CDMA 与 USB 回归、接线后的完整 ETM 验收。用户尚未接好 trace 线。
- 重建入口使用 `build/orbtrace_native32_idelay_build.log`；ELF 参数为
  `--max-swclk-hz 50000000`。下方旧日志和 60 MHz 参数仅用于历史排查。

## 当前已实现、待整体验收

- 基线 main dc95b99，分支 codex/orbtrace-cm3，原主目录未动。
- J7 连续 15–19 脚已接入 BD/XDC；16=H16 MRCC TRACECLK，15/17/18/19=D0/D1/D2/D3，14=GND。
- 板级 BUFIO/BUFR + SAME_EDGE_PIPELINED IDDR、4096 条 16-bit BRAM 记录 FIFO、0x40030000 AXI。
- 最初复位写法推导 latch 的问题已修复；新 OOC 综合确认 latch=0。
- 第一轮实现的 BUFG 输入 hold 问题已换用专用 I/O 时钟结构重新实现，仍在等待最终 STA/bit。
- 8 线程 SWD 子综合异常退出后，采用 ZYNQLINK_RUN_THREADS=1 重试，子综合已成功并进入布线。
- PS USB EP2 IN 0x82 独立 ETM，ZET1 + EP0 vendor 0x60；原 DAP/HSS/CDC/HID 保留。
- 生产 C 的 mocks 测试通过：描述符、EP2 IN 隔离、空结束包、发送重试、队列背压、USB reset epoch，
  原有 DAP/RTT/HSS 回归通过，增加 PS MEM-AP 计划读回标定。
- Web 位于本仓库 web/；九个页面含额外 RTT Viewer，纯静态页面 + 浏览器设备 API + OpenCSD WASM。
- 浏览器已验证九页导航；用户要求的 ETM、工程生成入口已平铺到调试器右边，更多功能菜单移除。
- Web 模块检查、协议/文件损坏负例、WASM 真 CM3 捕获、目标寄存器和锁恢复、工程生成/HSS 端点测试通过。
- CM3 用例已扩展为真实目标 -> BUFIO/BUFR -> pipelined IDDR -> ORBTrace -> BRAM -> PS AXI；
  100 MHz HCLK / 50 MHz TRACECLK：1949 字节、276 帧、22037 指令范围；160 MHz HCLK / 80 MHz
  TRACECLK + PS 读取停顿压力：3126 字节、443 帧、35360 范围。后者是功能压力用例，不是 50 MHz
  板级时序约束的验收。两个用例均与原版 ORBTrace 逐字节一致、OpenCSD flow 一致、无溢出。
- 新证据在 docs/validation/orbtrace-integration-20261030/，旧的 20261029 初始仿真记录保留。
- WASM 为 OpenCSD 1.8.3 / Emscripten 4.0.10，源码和产物均在项目内，build-manifest 已记录指纹。
- 用户已明确回复 trace 五根线“暂未接好”，完整实板 ETM 接收/解码验收仍待外部连线。

## 必须继续处理

- 等待/检查本次单线程重试的布线、全时钟 setup/hold 和 bitgen，不用旧 bit 冒充。
- 按最终通过的 FCLK 上限重新编译 ELF；保留实际 bit/ELF、SHA-256、时序与资源报告。
- 完成剩余浏览器交互验证、复现文档与源码/产物提交，避免批量提交 build 中间文件。
- 完整实板 trace 验收待接线；未完成时必须如实标注，保留已知可用 prebuilt，不标已上板通过。

## 运行入口与位置

- FPGA：python tools/run_vivado.py -mode batch -nojournal -log build/orbtrace_io_clock_retry.log
  -source fpga/build_dma.tcl -tclargs --fresh（环境 ZYNQLINK_RUN_THREADS=1）
- 固件：python tools/build_xusbps_daplink.py --project xusbps_daplink_dma --opt 3
  --max-swclk-hz 60000000 --bsp E:/zynqlinkPRO/reference/legacy_zynq/ZYNQ_DAPLINK_RTL_100TO50MHz/ZYNQ_DAPLINK_RTL_100TO50MHz.sdk/usb_bsp/ps7_cortexa9_0
- WASM：EM_CONFIG=build/emsdk/.emscripten，python build/emsdk/upstream/emscripten/emcmake.py
  cmake -S web/etm-native -B build/etm_wasm -G Ninja -DCMAKE_BUILD_TYPE=Release，
  cmake --build build/etm_wasm --target zynqdap_etm --parallel 6。
- 主目录另有其它 Vivado 进程；仅管理本 worktree 的进程，不中断其它构建。
