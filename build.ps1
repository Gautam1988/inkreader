# SPDX-License-Identifier: AGPL-3.0-or-later
# Builds dist\InkReader.exe (single file, no console window).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller==6.22.3
}
.\.venv\Scripts\python.exe make_icon.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name InkReader --icon inkreader.ico `
    --add-data "inkreader.ico;." --add-data "LICENSE;." --add-data "THIRD_PARTY_NOTICES.md;." `
    inkreader.py
Write-Host "Built: $PSScriptRoot\dist\InkReader.exe"
