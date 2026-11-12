# 从接线到验收

下面以 Windows、正式 J7 探针和 STM32H743 为例。先完成临时加载和目标烧录，再按需固化探针。每条命令成功后再执行下一条。换板时需要知道板子的芯片型号和接线，并准备适用于该板的固件。

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

结束后关闭本次浏览器标签页，在终端 A 按 Ctrl+C 停止服务。若只需要临时使用探针，到这里即可。

## 5. 固化探针并验证冷启动

这一步写 **Zynq 探针本体的 QSPI**。保留 Xilinx JTAG 下载线。停止工作台和采集，把探针启动拨码设为 QSPI 并给探针断电重上电。各板型拨码位置以板上丝印和原理图为准，下一条命令确认实际读回值。

1. 复查探针为空闲，并确认 `BOOT_MODE` 为 `0x1`。

   ```powershell
   python -X utf8 toolbox.py probe-load --check-only --out build/first-run-qspi-check
   ```

2. 离线核对正式 BOOT 包和 SHA-256。

   ```powershell
   python -X utf8 toolbox.py probe-flash --dry-run
   ```

3. 备份整片 QSPI，再写入正式 BOOT 镜像，独立读回比对并验证复位启动。等命令结束，确认 `result.json` 中的 `status` 为 `programmed_verified_reset_boot`、`outside_erased_range_unchanged` 为 `true`。备份位于同目录的 `original_flash_32MiB.bin`。

   ```powershell
   python -X utf8 toolbox.py probe-flash --out build/first-run-qspi-program
   ```

将探针本体实际断电后重新上电。等探针 USB 重新出现，保留 JTAG 下载线。此时可以直接做下列只读检查。

4. 核对板子从 QSPI 走完启动链，并比对正式 PS ELF 的 OCM 执行代码。成功时 `result.json` 显示 `"boot_mode": 1`、`"passed": true` 和 85,844 字节。

   ```powershell
   python -X utf8 toolbox.py project run probe.ocm-verify -- --elf prebuilt/release-20261106/application.elf --require-qspi --out-dir build/first-run-qspi-cold
   ```

若已有正式固化镜像，只想检查 BOOT 字节并验证复位启动，可使用 `probe-flash --verify-only`；实体冷启动仍用断电后的只读核对。其他芯片、CFG 导入、Trace、编译和故障处理命令见 [CLI 命令清单](toolbox-cli-ai.md)。
