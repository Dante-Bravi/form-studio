$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$bitmap = New-Object System.Drawing.Bitmap 64, 64
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = 'AntiAlias'
$graphics.Clear([System.Drawing.Color]::FromArgb(17, 20, 24))
$pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(106, 231, 180)), 7
$graphics.DrawLine($pen, 19, 47, 19, 17)
$graphics.DrawLine($pen, 19, 17, 46, 17)
$graphics.DrawLine($pen, 19, 31, 39, 31)
$icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
$stream = [System.IO.File]::Create((Join-Path $PSScriptRoot 'FORM.ico'))
try { $icon.Save($stream) } finally { $stream.Dispose(); $graphics.Dispose(); $pen.Dispose(); $bitmap.Dispose() }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /target:winexe "/out:$PSScriptRoot\FormStudio.exe" "/win32icon:$PSScriptRoot\FORM.ico" /reference:System.Windows.Forms.dll (Join-Path $PSScriptRoot 'FormLauncher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }
