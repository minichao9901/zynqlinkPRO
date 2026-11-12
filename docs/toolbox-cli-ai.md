# ZynqLinkPRO CLI 命令清单

第一次操作按 [从接线到验收](toolbox-cli-first-run.md) 依次完成。下文可按用途查单条命令。

在仓库根目录用 PowerShell 7 执行。输出目录示例均为新目录，重跑时换一个目录名。硬件操作前核对板卡和文件配对，结束正在运行的采集，并断开其他工作台或 CLI 对同一探针的连接。项目协作规则与故障记录见 [AGENTS.md](../AGENTS.md) 和 [项目问题跟踪列表](项目问题跟踪列表.md)。

[探针版本](#探针版本) · [探针临时加载](#探针-bit--elf-临时加载) · [探针 QSPI 固化](#探针-qspi-固化) · [启动与操作 Web](#启动与操作-web) · [目标 MCU 烧录](#目标-mcu-烧录) · [OpenOCD CFG](#openocd-wasm-目标配置) · [Trace](#etm-trace) · [构建与检查](#构建与检查)

## 探针版本

**当前 J7 日常使用 `prebuilt/release-20261106/` 的正式 bit + PS ELF。** 临时是指经 JTAG 加载后断电丢失。QSPI 启动包内的 bit 和 PS ELF 与这套正式文件的 SHA-256 分别相同，两种启动方式各用自己的初始化文件。

| 目录 | 用途 |
|---|---|
| [release-20261106](../prebuilt/release-20261106/README.md) | 当前正式 J7 配对。直接加载用同目录的 `probe.bit`、`application.elf` 和 `ps7_init.tcl`。 |
| [qspi-release-20261106](../prebuilt/qspi-release-20261106/README.md) | 当前正式 J7 QSPI 启动包。固化使用包内的 `BOOT.bin`，其中包含同一 bit/PS ELF 及 QSPI 启动链。 |
| [golden](../prebuilt/golden/README.md) | 旧 7020/120 MHz JTAG 基线，用于历史对照和回退。该目录里的 `f103ze-cdc48.elf` 另属目标 MCU 固件。 |
| [recovery](../prebuilt/recovery/README.md) | 旧 QSPI 恢复包，仅用于匹配原接线的回退。 |

## 查找命令

1. 查看统一 CLI 的顶层命令。

   ```powershell
   python -X utf8 toolbox.py --help
   ```

2. 离线列出 Web 页面、控件和方法的源码位置。

   ```powershell
   python -X utf8 toolbox.py catalog --full
   ```

3. 列出当前可运行的项目工具。

   ```powershell
   python -X utf8 toolbox.py project list
   ```

4. 查看探针回归套件的入口、依赖和使用范围。

   ```powershell
   python -X utf8 toolbox.py project describe probe.regression
   ```

5. 预览 Cortex-M3 JTAG 仿真命令，底层工具参数放在 `--` 后。

   ```powershell
   python -X utf8 toolbox.py project run sim.cm3 --dry-run -- --top tb_cm3_jtag
   ```

## 探针 bit + ELF 临时加载

使用 PC 到 **Zynq 探针本体**的 JTAG 下载线。临时加载会复位 Zynq、配置 FPGA、加载并运行 PS ELF。断电会丢失这次加载，探针 QSPI 和目标 MCU Flash 不写入。

1. 查看探针加载参数。

   ```powershell
   python -X utf8 toolbox.py probe-load --help
   ```

2. 离线核对正式 J7 配对及初始化 Tcl 的 SHA-256，打印实际加载计划。

   ```powershell
   python -X utf8 toolbox.py probe-load --dry-run
   ```

3. 只读检查 JTAG、启动模式和探针忙闲。

   ```powershell
   python -X utf8 toolbox.py probe-load --check-only --out build/probe-check-new
   ```

4. 临时加载正式 J7 的 bit 和 PS ELF，经物理 MEM-AP0 读回 OCM 执行代码并保存 `result.json`。

   ```powershell
   python -X utf8 toolbox.py probe-load --out build/probe-load-j7-new
   ```

5. 显式指定一套 bit、Zynq PS ELF 和 PS 初始化 Tcl。换配对时将三条路径一起替换为对应文件。

   ```powershell
   python -X utf8 toolbox.py probe-load --bit prebuilt/release-20261106/probe.bit --zynq-elf prebuilt/release-20261106/application.elf --ps-init prebuilt/release-20261106/ps7_init.tcl --out build/probe-load-explicit-new
   ```

6. 独立核对当前板上 OCM 执行代码与指定 PS ELF 是否一致，并记录 FCLK。

   ```powershell
   python -X utf8 toolbox.py project run probe.ocm-verify -- --elf prebuilt/release-20261106/application.elf --out-dir build/probe-identity-new
   ```

加载结果以 `result.json` 的 `passed` 为准。失败时查对应阶段日志，核对加载内容见 `ocm/result.json`。工具链安装见 [依赖说明](dependencies.md)。

## 探针 QSPI 固化

硬件操作需要 Zynq JTAG 下载线和空闲探针。写入或校验 BOOT 区要求上电读回 `BOOT_MODE=1`。默认 J7 镜像包为 `prebuilt/qspi-release-20261106/`，默认写入后端限 JEDEC EF4019 的 bank 0。备份留在本机。固化完成后执行实体断电重启，核对探针重新枚举及实际配对。[启动包和冷启动记录](../prebuilt/qspi-release-20261106/README.md)

1. 离线校验默认 BOOT 包并预览固化步骤。

   ```powershell
   python -X utf8 toolbox.py probe-flash --dry-run
   ```

2. 备份探针整片 QSPI，写入默认 BOOT 镜像，独立读回校验，核对擦写范围外内容并复位启动。

   ```powershell
   python -X utf8 toolbox.py probe-flash --out build/qspi-program-new
   ```

3. 只备份当前探针 QSPI。读取程序会接管 Zynq PS，备份完成后需手动恢复原运行方式。

   ```powershell
   python -X utf8 toolbox.py probe-flash --backup-only --out build/qspi-backup-new
   ```

4. 读回现有 BOOT 区并与镜像比较，随后复位测试启动。此操作无擦写。

   ```powershell
   python -X utf8 toolbox.py probe-flash --verify-only --out build/qspi-verify-new
   ```

5. 实体断电重启后检查 QSPI 启动交接、FCLK 和板上 OCM 执行代码。

   ```powershell
   python -X utf8 toolbox.py project run probe.ocm-verify -- --elf prebuilt/release-20261106/application.elf --require-qspi --out-dir build/qspi-cold-boot-new
   ```

6. 为自建 QSPI 包生成 SDK BSP。

   ```powershell
   python -X utf8 toolbox.py project run boot.bsp -- --out build/qspi-bsp-new
   ```

7. 使用上一步的 BSP 和配对产物编译 QSPI 加载器及读写辅助程序。

   ```powershell
   python -X utf8 toolbox.py project run boot.build -- --bsp build/qspi-bsp-new/bsp --bit prebuilt/release-20261106/probe.bit --elf prebuilt/release-20261106/application.elf --out build/qspi-loader-new
   ```

8. 使用支持 QSPI 的 PS 初始化 Tcl 生成 BOOT 镜像和 manifest。

   ```powershell
   python -X utf8 toolbox.py project run boot.package -- --loader-dir build/qspi-loader-new --bit prebuilt/release-20261106/probe.bit --elf prebuilt/release-20261106/application.elf --ps-init firmware/boot/hardware/ps7_init.tcl --output-dir build/qspi-package-new
   ```

9. 离线检查自建 BOOT 包并预览固化步骤。

   ```powershell
   python -X utf8 toolbox.py probe-flash --image-dir build/qspi-package-new --dry-run
   ```

10. 固化已核对的自建 BOOT 包并读回校验。

    ```powershell
    python -X utf8 toolbox.py probe-flash --image-dir build/qspi-package-new --out build/qspi-custom-program-new
    ```

固化成功时检查输出的 `result.json` 和 `readback_sha256`。旧 SDK 写入后端的故障记录见 ZL-167。[QSPI 启动链](../firmware/boot/README.md)

## 启动与操作 Web

在终端 A 启动以下任一服务，用浏览器打开该终端打印的鉴权 URL 并保持页面运行。控制命令在终端 B 执行，`--runtime` 填实际服务目录。URL 和令牌仅供本机使用。使用完毕可在终端 A 按 Ctrl+C 结束本次服务。

1. 启动源码工作台，浏览器可使用其 WebUSB 通路。选用此命令时，后续示例的运行目录换成 `build/workbench-web-new`。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-web-new serve --port 8878
   ```

2. 启动带本机 USB/HID/串口服务的工作台。这里声明板上已经加载的探针 bit 和 PS ELF，加载须先完成。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new serve --port 8878 --native-probe --bit prebuilt/release-20261106/probe.bit --zynq-elf prebuilt/release-20261106/application.elf
   ```

3. 检查浏览器 worker 是否就绪，无设备访问。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new ping
   ```

4. 查看工作台和命令队列摘要。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new status
   ```

5. 查看 CLI 可操作的页面标识。

   ```powershell
   python -X utf8 toolbox.py page --help
   ```

6. 查看串口助手的端口、波特率、连接及发送控件。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page serial describe
   ```

7. 设定串口助手的波特率。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page serial set '#s-baud' 115200
   ```

8. 打开串口助手已选中的端口，端口须先在页面选好。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page serial click '#s-open'
   ```

9. 关闭串口助手当前的端口。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page serial click '#s-close'
   ```

10. 连接调试器当前所选目标，等待网页连接方法结束。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page dbg invoke connect
    ```

11. 断开调试器，释放其探针连接。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page dbg invoke disconnect
    ```

12. 查看 RTT Viewer 的目标、ELF 和控制块设置。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page rtt describe
    ```

13. 按 RTT Viewer 已选的目标和控制块设置启动连接。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page rtt invoke connectProbe
    ```

14. 读取 RTT Viewer 的当前状态和连接摘要。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page rtt state
    ```

15. 断开 RTT Viewer。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page rtt invoke disconnect
    ```

16. 查看 J-Scope 的 ELF、变量和采样通路控件。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page scope describe
    ```

17. 按 J-Scope 已选的变量及采样设置启动采样。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page scope invoke start
    ```

18. 停止 J-Scope 采样。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page scope invoke stop
    ```

19. 查询已提交操作的结果。将 `JOB_ID` 替换为 CLI 返回的 ID，超时先查这个 ID 再决定后续操作。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new job JOB_ID
    ```

20. 读取本机探针服务的队列和资源状态，无板卡访问，可在浏览器未打开时使用。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new probe status
    ```

21. 取消指定会话的排队任务，运行中的操作在安全边界退出。将 `OWNER_ID` 替换为实际 owner。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new probe cancel --owner OWNER_ID
    ```

22. 查看原生探针服务的请求格式。调用 USB/HID/串口动作时按协议传递 owner 和 resourceEpoch。[服务协议与验收](validation/session-flight-recorder-20261105/README.md)

    ```powershell
    python -X utf8 toolbox.py probe call --help
    ```

`click`、`set` 和 `upload` 返回事件投递结果。业务完成情况通过页面状态、日志或操作结果核对。`invoke` 等待被调用的公开方法返回。

## 目标 MCU 烧录

1. 查看一条命令完成目标烧录和读回校验的参数。顺序操作见 [入门手册](toolbox-cli-first-run.md#4-烧录目标-mcu-并确认结果)。

   ```powershell
   python -X utf8 toolbox.py target-flash --help
   ```

### 逐项操作烧录页面

下面用仓库内的 F103ZE ELF 举例，会写入通过 SWD 连接的 **STM32F103ZE 目标 MCU**。换板时换成匹配的芯片、固件和频率，并先断开占用探针的页面。使用本机工作台时启用 `--native-probe`。

1. 打开烧录器页面。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash show
   ```

2. 列出烧录器可选芯片、时钟和文件控件。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash describe
   ```

3. 选择内置的 STM32F103 OpenOCD CFG。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash set '#f-chip' '"stm32f103"'
   ```

4. 将该次 SWD 烧录时钟设为 10 MHz，控件单位为 kHz。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash set '#f-speed' 10000
   ```

5. 上传目标 MCU ELF。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash upload '@file:view._fileInput' prebuilt/golden/f103ze-cdc48.elf
   ```

6. 等待页面显示已读入的 ELF 文件名。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash wait '#f-file-info' --contains 'f103ze-cdc48.elf'
   ```

7. 启用烧录后读回校验。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash set '#f-verify' true
   ```

8. 启用校验完成后的目标复位运行。任务要求烧完保持暂停时，将此布尔值改为 `false`。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash set '#f-reset' true
   ```

9. 执行目标 MCU 烧录及校验，CLI 最长等待 240 秒。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new --timeout 240 page flash invoke flash
   ```

10. 读取烧录结果，确认页面显示「读回校验通过」。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash read '#f-result'
    ```

11. 读取 OpenOCD 烧录日志，核对识别、写入和校验过程。

    ```powershell
    python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash read '#f-log'
    ```

## OpenOCD Wasm 目标配置

调试器、烧录器和 RTT Viewer 共用 OpenOCD Wasm。内置烧录列表提供与 Wasm 源码版本配对的 OpenOCD 原版 target CFG，以及 HPM SDK v1.11.0 原版 board、SoC 和入口 CFG。内置与手动导入共用解析入口。HPM 内置项通过 SDK 的 `BOARD` 和 `PROBE=cmsis_dap` 选择板卡及探针，包括 HPM6P00EVK。[H743 对照与 HPM 发布](validation/hpm-sdk-cfg-release-20261112/README.md)

在调试器断开时导入匹配且可信的 CFG。单文件直接上传。有 `source [find …]` 依赖时，上传脚本根目录再选入口。导入时在断开 USB 的 Worker 解析，目标事件在实际连接时执行。

1. 查看调试器当前的 CFG 导入控件、入口选项和核心列表。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page dbg describe
   ```

2. 导入单个 CFG，将示例路径替换为实际文件。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page dbg upload '#d-cfg-file' 'E:/configs/my-target.cfg'
   ```

3. 上传含依赖脚本的目录，保留目录内相对路径。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page dbg upload '#d-cfg-dir' 'E:/configs/openocd' --directory
   ```

4. 选择目录内的入口 CFG，将 `board/my-board.cfg` 换成上一步目录内实际入口的相对路径。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page dbg set '#d-cfg-entry' '"board/my-board.cfg"'
   ```

5. 读取当前导入的核心、CFG SHA-256、频率和 Flash 能力。结果为空时检查导入状态，选择 CFG 后应核对名称及哈希。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page dbg invoke cfgInfo
   ```

6. 让烧录器沿用已导入且声明 Flash bank 的目标。执行后检查烧录器的芯片下拉框。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page flash click '#f-use-session-target'
   ```

7. 让 RTT Viewer 沿用当前导入目标，随后选择匹配的 ELF 或填写控制块地址及 RAM 范围。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page rtt click '#r-use-session-target'
   ```

内置烧录默认 SWD 1 MHz、HPM JTAG 10 MHz。调试器、烧录器和 RTT Viewer 的内置 HPM 档最高 25 MHz，其他 ARM/RISC-V 最高 60 MHz。RTT Viewer 默认 10 MHz。导入项使用 CFG 自带频率，实际时钟以板上读回为准。J-Scope 自动模式在采样周期达到 10 ms 时使用 Wasm 轮询，短周期使用探针硬件采样。RTT 转发和硬件采样通过探针私有 HID 控制，数据走 CDC 和 HSS Bulk。[Wasm 迁移与验收范围](validation/openocd-wasm-20261108/README.md)

## ETM Trace

原生采集可直接从 CLI 操作。这里的 `--elf` 指目标 MCU ELF，`--zynq-elf` 指探针 PS ELF，`--bit` 与 `--zynq-elf` 须填写已加载配对。原生采集的 `--swd-khz` 单位为 kHz，底层 Trace Web 命令的 `--swd-hz` 单位为 Hz。[Trace CLI 参数和结果](Trace-CLI使用说明.md)

1. 离线检查原生采集依赖。

   ```powershell
   python -X utf8 toolbox.py trace doctor --offline
   ```

2. 查看原生采集参数。

   ```powershell
   python -X utf8 toolbox.py trace capture --help
   ```

3. 在实际运行匹配目标固件的 F103ZE 上采集 1 秒，SWD 请求 10 MHz，输出到新目录。

   ```powershell
   python -X utf8 toolbox.py trace capture --elf prebuilt/golden/f103ze-cdc48.elf --bit prebuilt/release-20261106/probe.bit --zynq-elf prebuilt/release-20261106/application.elf --out build/trace-f103-new --seconds 1 --swd-khz 10000
   ```

4. 离线查询上一步记录的摘要。

   ```powershell
   python -X utf8 toolbox.py trace query --record build/trace-f103-new --view summary
   ```

5. 将已有解码记录导出为可离线缩放的火焰图 HTML。

   ```powershell
   python -X utf8 toolbox.py trace export --record build/trace-f103-new --format flame-html --out build/trace-f103-flame.html
   ```

6. 使用冻结 EXE 导出同一记录的火焰图 HTML。

   ```powershell
   .\dist\zynq-etm-bridge\zynq-etm-bridge.exe --trace-cli export --record build/trace-f103-new --format flame-html --out build/trace-f103-exe-flame.html
   ```

7. 查看 ETM 页面的目标控制方法。

   ```powershell
   python -X utf8 toolbox.py --runtime build/workbench-j7-new page etm describe --target target
   ```

火焰图 HTML 包含 Timeline 和周期权重页，左键框选放大，Shift 拖动平移。Web 的 `history.exportFlame` 默认导出 HTML，可显式选择 SVG。[HTML 导出说明](flame-html-export.md)

## 构建与检查

1. 查看 FPGA 构建入口和工具链。

   ```powershell
   python -X utf8 toolbox.py project describe fpga.build
   ```

2. 预览 FPGA 构建命令。

   ```powershell
   python -X utf8 toolbox.py project run fpga.build --dry-run
   ```

3. 调用 Vivado 构建 FPGA bitstream，输出在项目构建目录，板卡无操作。

   ```powershell
   python -X utf8 toolbox.py project run fpga.build
   ```

4. 构建并验收 Windows EXE 候选，成功后更新日常目录并保留用户数据。

   ```powershell
   python -X utf8 toolbox.py bridge-build
   ```

5. 构建并更新 Windows EXE，额外生成含 `_internal` 的完整分发 ZIP。

   ```powershell
   python -X utf8 toolbox.py bridge-build --zip
   ```

6. 对固定目录里的冻结 EXE 做独立离线验收，输出写入新目录。

   ```powershell
   python -X utf8 toolbox.py project run bridge.verify -- --package dist/zynq-etm-bridge --out build/bridge-check-new
   ```

7. 核对随 Git 提供的依赖文件及其哈希。

   ```powershell
   python -X utf8 tools/verify_dependencies.py
   ```

8. 运行 Web 静态检查。

   ```powershell
   python -X utf8 toolbox.py project run web.check
   ```

9. 运行 Web 离线测试。

   ```powershell
   python -X utf8 toolbox.py project run test.web
   ```

10. 运行统一 CLI 主机测试。

    ```powershell
    python -X utf8 toolbox.py project run test.cli
    ```

11. 核对主工作台和 ETM 的共享驱动副本。

    ```powershell
    python -X utf8 toolbox.py project run web.shared-sync -- --check
    ```

12. 将主工作台的共享驱动同步到 ETM 副本。

    ```powershell
    python -X utf8 toolbox.py project run web.shared-sync -- --write
    ```

Windows 日常入口为 `dist/zynq-etm-bridge/zynq-etm-bridge.exe`，默认打开 Web，记录在旁边的 `data/records`。完整分发包需保留 `_internal`。测试可用 EXE 的 `--data-dir` 指定独立数据目录，`--offline` 可禁用 USB/HID/串口和采集。

## 研发验收工具

HPM 高频对照和 DDR 压力测试示例需要从 `archive/main-before-formal-release-20261106` 取回各自的实验配对。目录名和取回方法见 [正式产物索引](../prebuilt/README.md)。

1. 预览 HPM6800EVK 的原生 TCK、idle 和采样窗口对照。历史 66.667 MHz 结果限定于该配对、idle22 和 mode17。[HPM6800EVK 历史报告](validation/hpm6800-speed-completion-20261102/README.md)

   ```powershell
   python -X utf8 toolbox.py project run tools/validate_hpm6800_performance.py --dry-run -- --bit prebuilt/hpm6800-jtag66-133-20261102/probe.bit --elf prebuilt/hpm6800-jtag66-133-20261102/application.elf --out build/hpm-cli-high-new --speeds 66666667 --idle 22 --modes 17 --windows axi --loops 128 --repeats 3
   ```

2. 查看原生 HPM6800 RTT/HSS 的时钟、idle 及采样周期参数。

   ```powershell
   python -X utf8 toolbox.py project run tools/validate_hpm6800_streams.py -- --help
   ```

3. 查看原生 HPM6800 采样窗口与 idle 的矩阵扫描参数。

   ```powershell
   python -X utf8 toolbox.py project run tools/characterize_hpm6800_idle.py -- --help
   ```

4. 对已加载实验配对的 F103 执行 DDR Trace 压力测试，按实际连线替换 COM 口，采样后下载并用物理 MEM-AP0 核对缓冲。

   ```powershell
   python -X utf8 toolbox.py project run etm.ddr-trace-stress -- --pair prebuilt/etm-ddr-usb-raw4-20261101 --out build/ddr-trace-check-new --rounds 2 --seconds 1,2 --cdc-port COM34 --decode --verify-ddr-physical
   ```

5. 离线检查 FRM1 数据，将 `captured.frm1` 替换为实际输入路径。

   ```powershell
   python -X utf8 toolbox.py project run etm.framed -- captured.frm1 --out build/framed-check-new --tail-bytes 1 --trace-id 2
   ```

H743 ETMv4 连续采集见 [H743 综合报告](validation/h743-comprehensive-20261101/README.md)。PLL、AHB/APB 分频由目标固件管理。
