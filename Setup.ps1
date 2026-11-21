$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 x64 from python.org, then try again.' }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & .\Build-Launcher.ps1
    & .\.venv\Scripts\python.exe desktop_server.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Runtime verification failed.' }
    Write-Host 'Ready. Open FormStudio.exe.'
} finally { Pop-Location }
