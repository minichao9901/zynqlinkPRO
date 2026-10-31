# STM32F103 CDC ACM 固件烧录脚本（pyocd + CMSIS-DAP）
#
# 用法：
#   pwsh -NoProfile -File .\flash.ps1                 # 烧 fw-cb.bin（在线板 F103CB/R8）
#   pwsh -NoProfile -File .\flash.ps1 -Chip ze        # 目标板 F103ZE
#   pwsh -NoProfile -File .\flash.ps1 -Target stm32f103cb
#
# 注意：只写 Flash 并复位，不做整片擦除之外的破坏性操作。
param(
    [ValidateSet('cb', 'ze')][string]$Chip = 'cb',
    [string]$Target
)
$ErrorActionPreference = 'Stop'
if (-not $Target) { $Target = if ($Chip -eq 'ze') { 'stm32f103ze' } else { 'stm32f103cb' } }

$root = $PSScriptRoot
$binFile = Join-Path $root "fw-$Chip.bin"
if (-not (Test-Path $binFile)) { throw "找不到固件：$binFile（先跑 build.ps1 -Chip $Chip）" }

$pyocd = (Get-Command pyocd).Source
& $pyocd list

Write-Output "烧录 $binFile -> $Target @0x08000000"
& $pyocd flash -t $Target --base-address 0x08000000 $binFile
if ($LASTEXITCODE -ne 0) { throw "烧录失败（exit $LASTEXITCODE）" }

& $pyocd reset -t $Target
if ($LASTEXITCODE -ne 0) { throw "复位失败（exit $LASTEXITCODE）" }
Write-Output "已复位。建议随后："
Write-Output "  1) 等 5~8 秒让 Windows 枚举（首次可能要清一次设备管理器里的坏节点）"
Write-Output "  2) python .\tools\min_probe.py --target $Target --read 0x20004fc0:56"
Write-Output "  3) python ..\tools\cdc_test.py --list  然后 --port COMx"
