# 从接线到验收

下面以 Windows、正式 J7 探针和 STM32H743 为例。先完成临时加载和目标烧录，再按需固化探针。每条命令成功后再执行下一条。换板时需要知道板子的芯片型号和接线，并准备适用于该板的固件。

从本机启动器打开工作台后，可在顶部选择「可执行手册」。按钮使用当前工作台和仓库，结果显示在对应命令下面。使用源码时，先在终端运行第 3 节的启动命令打开页面。便携版工作台位于仓库的 `dist` 内时会自动找到仓库，独立解压时可在启动 EXE 时用 `--workspace` 指定仓库。执行 CLI 命令需要系统 Python。

## 1. 检查主机环境

1. 在 PowerShell 7 进入仓库根目录。仓库在别处时，替换示例路径。

   ```powershell
   Set-Location 'E:/zynqlinkPRO'
   ```

2. 检查 Python 是否可用。示例在 Python 3.13 下执行。

   ```powershell
   python --version
   ```

3. 首次使用源码工作台时，安装服务、USB 和 XSCT 启动器所需的 Python 包。

   ```powershell
   python -m pip install -r etm-service/requirements.txt pefile
   ```

4. 核对随仓库提供的构建依赖文件。结果应有 `"ok": true`。探针 JTAG 操作另需安装 Xilinx SDK 2018.3，默认路径为 `E:/Xilinx/SDK/2018.3`，装在其他位置时向探针命令传入 `--sdk`。[安装与换机说明](dependencies.md)

   ```powershell
   python -X utf8 tools/verify_dependencies.py
   ```

## 2. 临时加载正式探针

接好 PC 到 **Zynq 探针本体**的 Xilinx JTAG 下载线，以及探针到 PC 的 USB 数据线。给探针供电。若探针已在使用，先停止采集并断开原工作台。目标 MCU 这时可以尚未接入。

1. 离线核对正式 J7 的 bit、PS ELF 和初始化 Tcl。命令会打印三份文件的路径和 SHA-256。

   ```powershell
   python -X utf8 toolbox.py probe-load --dry-run
   ```

2. 只读检查 Zynq JTAG、启动拨码和采集忙闲。看到 `"passed": true` 再继续。失败先检查 JTAG 下载线、供电、驱动及占用。后续若要固化，要求这里的 `BOOT_MODE` 为 `0x1`。

   ```powershell
   python -X utf8 toolbox.py probe-load --check-only --out build/first-run-probe-check
   ```

3. 临时加载正式 J7 FPGA bit 和 Zynq PS ELF，并读回 OCM 执行代码。成功时显示 `"passed": true` 和 `"verifiedBytes": 85844`，详细结果在输出目录的 `result.json`。USB 在 Zynq 复位期间会重新枚举。

   ```powershell
   python -X utf8 toolbox.py probe-load --out build/first-run-probe-load
   ```

重复演练时，换一组尚未存在的输出和运行目录名，并在后续命令里使用相同的新名字。

## 3. 启动工作台并读取目标身份

在断电或安全接线的状态下，按 J7 针脚表接好目标 SWDIO、SWCLK 和共地，核对 I/O 电平并给目标供电。计划使用探针硬复位时再接 NRST。若接线期间给 Zynq 断了电，重新执行第 2 节的临时加载步骤。[J7 针脚表](../README.md#硬件与接线)

1. 在终端 A 启动本机工作台。自动选择空闲端口并打开浏览器，保持终端和网页运行。如果浏览器没打开，将终端打印的 `browserUrl` 粘到 Chrome 或 Edge。这个 URL 带本机令牌。

   ```powershell
   python -X utf8 toolbox.py --runtime build/first-run-web serve --j7 --port 0 --open-browser
   ```

2. 打开终端 B，进入同一个仓库目录。

   ```powershell
   Set-Location 'E:/zynqlinkPRO'
   ```

3. 确认网页已经接上 CLI 队列。结果应有 `"ok": true`。如果报未就绪，等网页打开并完全加载后再执行此命令。

   ```powershell
   python -X utf8 toolbox.py --runtime build/first-run-web ping
   ```

4. 输入要烧录的 **H743 目标固件**的绝对路径并回车。示例使用适配这块板的 ELF，路径含空格时直接输入完整路径即可。

   ```powershell
   $Firmware = Read-Host '输入 H743 固件 ELF 的绝对路径'
   ```

5. 解析该文件、选择 STM32H7 和 10 MHz SWD，并显示待写地址、长度和固件哈希。看到 `"prepared": true` 再继续。此步不连接设备。

   ```powershell
   python -X utf8 toolbox.py --runtime build/first-run-web target-flash --chip stm32h7 --swd-khz 10000 --file "$Firmware" --prepare-only
   ```

6. 读取目标身份。STM32H743 所在系列的 `devId` 是 1104（十六进制 `0x450`），并需结合板上丝印确认是 H743。若身份为空或不符，先检查供电、SWD 接线和选中的目标。

   ```powershell
   python -X utf8 toolbox.py --runtime build/first-run-web page flash invoke readIdcode
   ```

## 4. 烧录目标 MCU 并确认结果

确认这块目标允许覆盖其 Flash，且上一步的地址和长度符合预期。需要保留原固件时先做好该目标的备份。

1. 用刚检查过的文件烧录 H743。命令通过网页的 OpenOCD Wasm 烧录器擦写、读回校验并复位运行。成功时返回 `"verified": true`、`"reset": true` 和实际写入字节数。

   ```powershell
   python -X utf8 toolbox.py --runtime build/first-run-web --timeout 240 target-flash --chip stm32h7 --swd-khz 10000 --file "$Firmware"
   ```

2. 核对页面结果显示「读回校验通过」。

   ```powershell
   python -X utf8 toolbox.py --runtime build/first-run-web page flash read '#f-result'
   ```

3. 查看识别、擦写、校验和复位日志。接下来按你烧入的固件定义检查串口、指示灯或其他应用功能。

   ```powershell
   python -X utf8 toolbox.py --runtime build/first-run-web page flash read '#f-log'
   ```

4. 若 CLI 等待超时，用错误消息中的 job ID 查询原操作。将 `JOB_ID` 换成实际值，等操作结束再决定下一步。

   ```powershell
   python -X utf8 toolbox.py --runtime build/first-run-web job JOB_ID
   ```

若只需要临时使用探针，到这里即可。在终端操作时，关闭标签页并按 Ctrl+C 结束服务。继续使用可执行手册固化时，保留手册页面，先断开调试连接并停止采集。

## 5. 固化探针并验证冷启动

这一步写 **Zynq 探针本体的 QSPI**。保留 Xilinx JTAG 下载线。确认工作台内的探针连接和采集已结束，把探针启动拨码设为 QSPI 并给探针断电重上电。各板型拨码位置以板上丝印和原理图为准，下一条命令确认实际读回值。

1. 复查探针为空闲，并确认 `BOOT_MODE` 为 `0x1`。

   ```powershell
   python -X utf8 toolbox.py probe-load --check-only --out build/first-run-qspi-check
   ```

2. 离线核对 [J7 正式 BOOT 包](../prebuilt/qspi-release/README.md)和 SHA-256。确认 `image_dir` 指向固定目录 `prebuilt/qspi-release/`。

   ```powershell
   python -X utf8 toolbox.py probe-flash --dry-run
   ```

3. 备份整片 QSPI，再写入正式 BOOT 镜像，独立读回比对并验证复位启动。等命令结束，确认 `result.json` 中的 `status` 为 `programmed_verified_reset_boot`、`outside_erased_range_unchanged` 为 `true`。备份位于同目录的 `original_flash_32MiB.bin`。

   ```powershell
   python -X utf8 toolbox.py probe-flash --out build/first-run-qspi-program
   ```

4. 已决定跳过原镜像备份时，用以下命令替代第 3 步。命令仍逐字节核对 BOOT 并验证复位启动。写前备份是比较擦写范围外字节的依据，这种模式只校验 BOOT。

   ```powershell
   python -X utf8 toolbox.py probe-flash --skip-backup --out build/first-run-qspi-program-no-backup
   ```

将探针本体实际断电后重新上电。等探针 USB 重新出现，保留 JTAG 下载线。此时可以直接做下列只读检查。

5. 核对板子从 QSPI 走完启动链，并比对正式 PS ELF 的 OCM 执行代码。成功时 `result.json` 显示 `"boot_mode": 1`、`"passed": true` ，并列出与正式 ELF 一致的执行段。

   ```powershell
   python -X utf8 toolbox.py project run probe.ocm-verify -- --elf prebuilt/qspi-release/application.elf --require-qspi --out-dir build/first-run-qspi-cold
   ```

若已有正式固化镜像，只想检查 BOOT 字节并验证复位启动，可使用 `probe-flash --verify-only`；实体冷启动仍用断电后的只读核对。其他芯片、CFG 导入、Trace、编译和故障处理命令见 [CLI 命令清单](toolbox-cli-ai.md)。

## 6. 重新打包 QSPI 镜像

本流程用 Xilinx SDK 2018.3 从专用启动 HDF 生成 BSP，再用正式 J7 bit 和 PS ELF 生成新的 BOOT.bin。本机工作台每次点第 1 步都会开启一个新目录，后续按钮使用同一组产物。使用终端时请为每轮换一个新的 `build/qspi-repack-new` 目录名，并在整组命令中使用同一名称。前四步可在探针断开的情况下完成。

1. 从仓库中的启动 HDF 生成并编译 QSPI BSP。

   ```powershell
   python -X utf8 toolbox.py project run boot.bsp -- --out build/qspi-repack-new/platform
   ```

2. 编译两阶段启动程序和 QSPI 读写辅助程序，使用正式 J7 bit 和 PS ELF 生成 BOOT.bin。

   ```powershell
   python -X utf8 toolbox.py project run boot.build -- --bsp build/qspi-repack-new/platform/bsp --bit prebuilt/qspi-release/probe.bit --elf prebuilt/qspi-release/application.elf --out build/qspi-repack-new/loader
   ```

3. 校验分区与输入配对，把 BOOT.bin、辅助程序和清单打到新的镜像目录。

   ```powershell
   python -X utf8 toolbox.py project run boot.package -- --loader-dir build/qspi-repack-new/loader --bit prebuilt/qspi-release/probe.bit --elf prebuilt/qspi-release/application.elf --ps-init firmware/boot/hardware/ps7_init.tcl --output-dir build/qspi-repack-new/image
   ```

4. 离线核对新包的文件哈希，并确认计划里的 `image_dir` 指向本次重包结果。

   ```powershell
   python -X utf8 toolbox.py probe-flash --image-dir build/qspi-repack-new/image --dry-run
   ```

5. 若要写入这个新包，先按第 5 节第 1 步确认探针空闲且 `BOOT_MODE=0x1`，再执行下列命令。写后按第 5 节断电重上电并核对 OCM，核对命令的 `--elf` 指向本次重包目录的 `application.elf`。

   ```powershell
   python -X utf8 toolbox.py probe-flash --image-dir build/qspi-repack-new/image --out build/qspi-repack-new/programmed
   ```
