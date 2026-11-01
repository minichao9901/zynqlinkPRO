param(
    [Parameter(Mandatory)][string]$Elf,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$ocd = Join-Path $repo 'prebuilt/golden/host/openocd/openocd.exe'
$scripts = Join-Path $repo 'prebuilt/golden/host/openocd/scripts'
$image = (Resolve-Path -LiteralPath $Elf).Path.Replace('\', '/')
if ($image -match '[{}\r\n]') { throw 'Unsafe Tcl image path' }
if (-not $Execute) { Write-Output "Plan only: program and verify H743 Flash from $image; use -Execute"; exit 0 }
$options = @('-s', $scripts, '-f', 'interface/cmsis-dap.cfg', '-c', 'transport select swd',
    '-f', 'target/stm32h7x.cfg', '-c', 'adapter speed 1000', '-c', 'init', '-c', 'halt',
    '-c', 'mww 0xe000ed0c 0x05fa0004', '-c', 'sleep 300', '-c', 'halt', '-c', 'mww 0xe000e010 0')
for ($i = 0; $i -lt 8; $i++) { $options += @('-c', ('mww 0x{0:x} 0xffffffff' -f (0xe000e180 + 4*$i))) }
$options += @('-c', "flash write_image erase {$image}", '-c', "verify_image {$image}",
    '-c', 'mww 0xe000ed0c 0x05fa0004', '-c', 'sleep 500', '-c', 'shutdown')
& $ocd @options
if ($LASTEXITCODE -ne 0) { throw "H743 programming/verification failed: $LASTEXITCODE" }
