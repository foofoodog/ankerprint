$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent $PSScriptRoot
Set-Location $RepoDir

if (-not (Test-Path "venv")) {
    Write-Host "[*] Creating virtual environment..."
    python -m venv venv
    & .\venv\Scripts\python.exe -m pip install --upgrade pip
}

Write-Host "[*] Installing dependencies & PyInstaller..."
& .\venv\Scripts\pip.exe install -r requirements.txt
& .\venv\Scripts\pip.exe install pyinstaller

Write-Host "[*] Compiling standalone executable..."
& .\venv\Scripts\pyinstaller.exe --clean -y `
    --onefile `
    --name ankerprint.exe `
    --collect-all bleak `
    --collect-all Cryptodome `
    --collect-all tinyec `
    ankerprint.py

Write-Host "[*] Build complete: dist\ankerprint.exe"
