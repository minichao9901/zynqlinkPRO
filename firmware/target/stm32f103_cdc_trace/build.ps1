# STM32F103 + CherryUSB CDC ACM + etm-trace 钩子 —— GCC 构建脚本
#
# 用法：
#   pwsh -NoProfile -File .\build.ps1                 # 默认 -Chip cb（在线板 F103CB/R8，64K/20K）
#   pwsh -NoProfile -File .\build.ps1 -Chip ze        # F103ZE，默认 CPU 48 / TRACECLK 24 MHz
#   pwsh -NoProfile -File .\build.ps1 -Chip ze -CpuMHz 72 # 72/36 MHz 对照档 fw-ze-72.*
#
# 产物：build\<chip>\fw.{elf,bin,hex}，并在根目录放 fw-<chip>.* 副本。
# 本脚本**只编译不烧录**；烧录用 flash.ps1。
#
# 首次构建前请确认 tools\prep.ps1 已跑过（build.ps1 会自动调用一次，幂等）。
param(
    [ValidateSet('cb', 'ze')][string]$Chip = 'cb',
    [string]$Gcc,
    [switch]$StandaloneEtm,
    [ValidateSet(24, 48, 72)][int]$CpuMHz = 72,
    [switch]$TraceWorkload
)
$ErrorActionPreference = 'Stop'
$explicitCpuMHz = $PSBoundParameters.ContainsKey('CpuMHz')
if ($Chip -eq 'ze' -and -not $explicitCpuMHz) { $CpuMHz = 48 }
if ($StandaloneEtm -and $Chip -ne 'ze') { throw '独立 ETM 模式仅支持 F103ZE' }
Import-Module (Join-Path $PSScriptRoot 'tools\BuildTools.psm1') -Force

$root = $PSScriptRoot
if (-not $Gcc) { $Gcc = (Get-Command arm-none-eabi-gcc).Source }
$bin  = Split-Path -Parent $Gcc
$sdk  = Join-Path $root 'sdk\Drivers'
$variant = if ($StandaloneEtm) { "$Chip-standalone" } else { $Chip }
if (($CpuMHz -in @(24, 48) -and ($explicitCpuMHz -or $StandaloneEtm -or $TraceWorkload)) -or
    ($Chip -eq 'ze' -and $CpuMHz -eq 72)) { $variant += "-$CpuMHz" }
if ($TraceWorkload) { $variant += '-workload' }
$out  = Join-Path $root "build\$variant"
New-Item -ItemType Directory -Path $out -Force | Out-Null

# ---------- 构建前准备：解开 ST 启动文件的 USB 中断弱别名锁定 ----------
# prep.ps1 是幂等的，启动文件已补丁（残留弱别名 = 0）。
# 这里不再每次调用 pwsh 子进程（它在 bash/make 环境下找不到 pwsh，会卡住构建）；
# 需要重新打补丁时手动运行：pwsh -NoProfile -File tools\prep.ps1

switch ($Chip) {
    'cb' { $def = 'STM32F103xB'; $startup = 'startup_stm32f103xb.s'; $ld = 'stm32f103cb.ld' }
    'ze' { $def = 'STM32F103xE'; $startup = 'startup_stm32f103xe.s'; $ld = 'stm32f103ze.ld' }
}

$flags = @(
    '-mcpu=cortex-m3', '-mthumb',
    '-Og', '-g3', '-gdwarf-4',
    '-fno-inline', '-fno-optimize-sibling-calls',
    '-ffunction-sections', '-fdata-sections', '-fno-common',
    '-Wall', '-Wextra', '-Wno-unused-parameter', '-Wno-unused-function',
    "-D$def", '-DUSE_HAL_DRIVER', '-DHSE_VALUE=8000000',
    # SEGGER RTT 控制块固定到 .rtt_cb（链接脚本放在 RAM 末尾）
    '-DRTT_CB_ATTR=__attribute__((section(".rtt_cb"),aligned(4)))',
    "-I$root\src",
    "-I$root\sdk",                                  # stm32f1xx_hal_conf.h 在这
    "-I$sdk\STM32F1xx_HAL_Driver\Inc",
    "-I$sdk\STM32F1xx_HAL_Driver\Inc\Legacy",
    "-I$sdk\CMSIS\Device\ST\STM32F1xx\Include",
    "-I$sdk\CMSIS\Include",
    "-I$root\segger_rtt",
    "-I$root\cherryusb\config",
    "-I$root\cherryusb\core",
    "-I$root\cherryusb\class\cdc",
    "-I$root\cherryusb\common",
    "-I$root\cherryusb\port\fsdev"
)
if ($StandaloneEtm) { $flags += '-DTRACE_ETM_STANDALONE' }
if ($CpuMHz -eq 24) { $flags += '-DTRACE_CPU_24MHZ' }
elseif ($CpuMHz -eq 48) { $flags += '-DTRACE_CPU_48MHZ' }
else { $flags += '-DTRACE_CPU_72MHZ' }
if ($TraceWorkload) { $flags += '-DTRACE_PATH_WORKLOAD' }

# ---------- 源文件 ----------
$sources = @(
    # 应用层
    "$root\src\main.c",
    "$root\src\cdc_console.c",
    "$root\src\trace_hooks.c",
    "$root\src\trace_workload.c",
    "$root\src\syscalls.c",
    # HAL 板级（沿用参照工程）
    "$root\src\system_stm32f1xx.c",
    "$root\src\stm32f1xx_hal_msp.c",
    "$root\src\stm32f1xx_it.c",
    # 日志
    "$root\segger_rtt\SEGGER_RTT.c",
    "$root\segger_rtt\SEGGER_RTT_printf.c",
    # CherryUSB（core + CDC 类 + fsdev port + glue）
    "$root\cherryusb\core\usbd_core.c",
    "$root\cherryusb\class\cdc\usbd_cdc_acm.c",
    "$root\cherryusb\port\fsdev\usb_dc_fsdev.c",
    "$root\cherryusb\port\fsdev\usb_glue_st.c"
)

# HAL 模块：只挑用得到的（注意 **不含** stm32f1xx_hal_pcd.c —— USB 状态机是 CherryUSB 自己的，
# 我们只需要 hal_conf.h 里 HAL_PCD_MODULE_ENABLED 带进来的 PCD_xxx 宏）
foreach ($m in @('hal','hal_cortex','hal_rcc','hal_rcc_ex','hal_gpio','hal_gpio_ex',
                 'hal_flash','hal_flash_ex','hal_dma','hal_exti','hal_pwr','hal_uart')) {
    $sources += Join-Path $sdk "STM32F1xx_HAL_Driver\Src\stm32f1xx_$m.c"
}

$startupPath = Join-Path $sdk "CMSIS\Device\ST\STM32F1xx\Source\Templates\gcc\$startup"

# ---------- 编译 ----------
# ⚠️ startup.o 必须排在**最前面**（标准做法，也让调试时向量表归属更清晰）
$startupObj = Join-Path $out 'startup.o'
$r = Invoke-Tool -Exe $Gcc -Args (@($flags) + @('-c', $startupPath, '-o', $startupObj))
if ($r.ExitCode -ne 0) { throw "编译失败：$startupPath" }

$objects = @($startupObj)
foreach ($src in $sources) {
    if (-not (Test-Path $src)) { throw "源文件不存在：$src" }
    $obj = Join-Path $out ([IO.Path]::GetFileNameWithoutExtension($src) + '.o')
    $r = Invoke-Tool -Exe $Gcc -Args (@($flags) + @('-c', $src, '-o', $obj))
    if ($r.ExitCode -ne 0) { throw "编译失败：$src" }
    $objects += $obj
}

# ---------- 链接 ----------
# 不能加 -nostartfiles：ST 启动文件里有 `bl __libc_init_array`，_init 由 crti.o 提供
$elf = Join-Path $out 'fw.elf'
$r = Invoke-Tool -Exe $Gcc -Args (@($flags) + @($objects) + @("-T$root\ld\$ld",
    '-specs=nano.specs', '-specs=nosys.specs', '-Wl,--gc-sections',
    "-Wl,-Map=$out\fw.map", '-o', $elf))
if ($r.ExitCode -ne 0) { throw '链接失败' }

foreach ($fmt in @(@('binary','bin'), @('ihex','hex'))) {
    $r = Invoke-Tool -Exe "$bin\arm-none-eabi-objcopy.exe" -Args @('-O', $fmt[0], $elf, "$out\fw.$($fmt[1])")
    if ($r.ExitCode -ne 0) { throw '格式转换失败' }
}
Write-Output (Invoke-Tool -Exe "$bin\arm-none-eabi-size.exe" -Args @($elf)).Stdout
(Invoke-Tool -Exe "$bin\arm-none-eabi-nm.exe" -Args @('-n', '-S', $elf)).Stdout | Set-Content -LiteralPath "$out\fw.symbols.txt" -Encoding utf8
(Invoke-Tool -Exe "$bin\arm-none-eabi-objdump.exe" -Args @('-d', '-S', $elf)).Stdout | Set-Content -LiteralPath "$out\fw.disasm.txt" -Encoding utf8

foreach ($ext in @('elf','bin','hex')) {
    Copy-Item -LiteralPath "$out\fw.$ext" -Destination "$root\fw-$variant.$ext" -Force
}

# ---------- 自检：USB 两个中断向量必须指向 CherryUSB 的处理函数 ----------
$vecTmp = Join-Path $out '_isr_vector.bin'
$null = Invoke-Tool -Exe "$bin\arm-none-eabi-objcopy.exe" -Args @('-O', 'binary', '--only-section=.isr_vector', $elf, $vecTmp)
$vec = [IO.File]::ReadAllBytes($vecTmp)
Remove-Item $vecTmp -Force -ErrorAction SilentlyContinue
$syms = ((Invoke-Tool -Exe "$bin\arm-none-eabi-nm.exe" -Args @($elf)).Stdout) -split "`r?`n"
function SymAddr([string]$name) {
    $hit = $syms | Select-String -Pattern ("^([0-9a-f]{8}) \S " + [regex]::Escape($name) + '$') | Select-Object -First 1
    if ($hit) { return ('0x' + $hit.Matches[0].Groups[1].Value) } else { return '(未定义)' }
}
$lpAddr = [BitConverter]::ToUInt32($vec, (16 + 20) * 4) # IRQ20: USB_LP_CAN1_RX0
$hpAddr = [BitConverter]::ToUInt32($vec, (16 + 19) * 4) # IRQ19: USB_HP_CAN1_TX
Write-Output "构建完成：chip=$variant ($def) -> $elf"
Write-Output ("向量表：USB_LP=0x{0:x8}  USB_HP=0x{1:x8}" -f $lpAddr, $hpAddr)
Write-Output ("符号表：USB_LP_IRQHandler={0}  USB_HP_IRQHandler={1}  Default_Handler={2}" -f `
    (SymAddr 'USB_LP_CAN1_RX0_IRQHandler'), (SymAddr 'USB_HP_CAN1_TX_IRQHandler'), (SymAddr 'Default_Handler'))
# 自检：向量存储的是 Thumb 地址（函数地址 bit0=1），必须匹配对应处理函数。
$dflt = SymAddr 'Default_Handler'
$lpSym = SymAddr 'USB_LP_CAN1_RX0_IRQHandler'
$hpSym = SymAddr 'USB_HP_CAN1_TX_IRQHandler'
if ($lpSym -eq '(未定义)' -or $hpSym -eq '(未定义)' -or $dflt -eq '(未定义)') {
    throw "USB 向量自检失败：符号缺失（LP=$lpSym HP=$hpSym Default=$dflt）"
} elseif (($lpAddr -band 0xfffffffeL) -ne [Convert]::ToUInt32($lpSym.Substring(2), 16) -or
          ($hpAddr -band 0xfffffffeL) -ne [Convert]::ToUInt32($hpSym.Substring(2), 16)) {
    throw ('USB 向量自检失败：LP=0x{0:x8}（应为 {1}+1）；HP=0x{2:x8}（应为 {3}+1）；Default={4}' -f `
        $lpAddr, $lpSym, $hpAddr, $hpSym, $dflt)
} else {
    Write-Output "自检通过：USB HP/LP 向量分别指向对应处理函数（Thumb bit 已校验）"
}
Write-Output "诊断变量地址："
Select-String -Path "$out\fw.symbols.txt" -Pattern ' g_trace$| _SEGGER_RTT$' | ForEach-Object { "  " + $_.Line }
