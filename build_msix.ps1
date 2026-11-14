# SPDX-License-Identifier: AGPL-3.0-or-later
# Builds an MSIX package of InkReader for the Microsoft Store (or for local testing).
#
# Local test build:
#   powershell -ExecutionPolicy Bypass -File build_msix.ps1
#   Then, with Windows Developer Mode on (Settings > System > For developers), install the unpacked layout:
#   Add-AppxPackage -Register build\msix\layout\AppxManifest.xml
#   (Remove it again with: Get-AppxPackage InkReader.LocalTest | Remove-AppxPackage)
#
# Store build - copy the three values from Partner Center > your app > Product identity:
#   powershell -ExecutionPolicy Bypass -File build_msix.ps1 `
#       -IdentityName "Aexonlab.InkReader" -Publisher "CN=XXXXXXXX-XXXX-..." -PublisherDisplayName "Aexonlab"
# Upload the resulting dist\InkReader-<version>-x64.msix in Partner Center; the Store signs it.
param(
    [string]$IdentityName = "InkReader.LocalTest",
    [string]$Publisher = "CN=InkReaderLocalTest",
    [string]$PublisherDisplayName = "GautamMohan"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    python -m venv .venv
    & $py -m pip install -r requirements.txt pyinstaller==6.22.3
}

# Version comes from inkreader.py (e.g. 1.5.1 -> 1.5.1.0; the Store needs the last part to be 0)
$ver = (Select-String -Path inkreader.py -Pattern '^VERSION = "([\d.]+)"').Matches[0].Groups[1].Value
$parts = @($ver.Split(".")) + @("0", "0", "0")
$msixVersion = ($parts[0..2] -join ".") + ".0"

# Windows SDK tools (MakeAppx, MakePri)
$sdk = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "x64\makeappx.exe") } | Sort-Object Name -Descending | Select-Object -First 1
if (-not $sdk) { throw "Windows 10/11 SDK not found (needed for makeappx.exe / makepri.exe)." }
$tools = Join-Path $sdk.FullName "x64"

$root = Join-Path $PSScriptRoot "build\msix"
$layout = Join-Path $root "layout"
if (Test-Path $root) { Remove-Item $root -Recurse -Force }
New-Item -ItemType Directory -Force $layout | Out-Null

# 1. Folder build (starts faster than the single-file exe: nothing to unpack on launch)
& $py make_icon.py | Out-Null
& $py -m PyInstaller --noconfirm --clean --onedir --windowed --name InkReader `
    --icon "$PSScriptRoot\inkreader.ico" `
    --add-data "$PSScriptRoot\inkreader.ico;." --add-data "$PSScriptRoot\LICENSE;." `
    --add-data "$PSScriptRoot\THIRD_PARTY_NOTICES.md;." `
    --distpath "$root\dist" --workpath "$root\work" --specpath $root `
    "$PSScriptRoot\inkreader.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Copy-Item "$root\dist\InkReader\*" $layout -Recurse

# 2. Tile and logo images
& $py packaging\make_store_assets.py "$layout\Assets"

# 3. Manifest
$manifest = (Get-Content packaging\AppxManifest.template.xml -Raw).
    Replace("{IDENTITY_NAME}", $IdentityName).Replace("{PUBLISHER}", [Security.SecurityElement]::Escape($Publisher)).
    Replace("{PUBLISHER_DISPLAY_NAME}", [Security.SecurityElement]::Escape($PublisherDisplayName)).
    Replace("{VERSION}", $msixVersion)
$localTest = $IdentityName -eq "InkReader.LocalTest"
[IO.File]::WriteAllText("$layout\AppxManifest.xml", $manifest, (New-Object Text.UTF8Encoding $false))

# 4. Resource index (lets Windows pick the right image scale / size)
& "$tools\makepri.exe" createconfig /cf "$root\priconfig.xml" /dq en-US /pv 10.0.0 /o | Out-Null
# One resources.pri for a single package (no per-scale split files, which are meant for bundles)
[xml]$pc = Get-Content "$root\priconfig.xml"
$pk = $pc.SelectSingleNode("//packaging")
if ($pk) { [void]$pk.ParentNode.RemoveChild($pk) }
$pc.Save("$root\priconfig.xml")
& "$tools\makepri.exe" new /pr $layout /cf "$root\priconfig.xml" /mn "$layout\AppxManifest.xml" /of "$layout\resources.pri" /o | Out-Null
if ($LASTEXITCODE) { throw "makepri failed" }

# 5. Pack
New-Item -ItemType Directory -Force dist | Out-Null
$suffix = if ($localTest) { "-localtest" } else { "" }
$out = Join-Path $PSScriptRoot "dist\InkReader-$msixVersion-x64$suffix.msix"
& "$tools\makeappx.exe" pack /d $layout /p $out /o
if ($LASTEXITCODE) { throw "makeappx failed" }
Write-Host "Built: $out  (identity: $IdentityName, publisher: $Publisher)"
