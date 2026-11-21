param([int]$Camera = 0, [string]$Esp32Port, [switch]$SecondEsp32)
$env:PYTHONPATH = Join-Path $PSScriptRoot '.training-deps'
$env:MPLCONFIGDIR = Join-Path $PSScriptRoot '.training-deps/mpl-cache'
$python = Join-Path $PSScriptRoot 'runtime/python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Extract the complete release ZIP, or run Setup.ps1 first.' }
$cameraArgs = @('--camera', $Camera)
if ($Esp32Port) { $cameraArgs += @('--esp32-port', $Esp32Port) }
& $python (Join-Path $PSScriptRoot 'live_camera.py') @cameraArgs
exit $LASTEXITCODE
