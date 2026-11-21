# Build Aster desktop GUI (Aster.exe)
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$buildDir = Join-Path $root "build"
$distDir = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$webData = (Join-Path $root "aster\webui") + ";aster/webui"
$assetData = (Join-Path $root "assets") + ";assets"
$icon = Join-Path $root "assets\aster.ico"

Write-Host "Building Aster.exe (GUI) ..." -ForegroundColor Cyan
$args = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "Aster",
    "--icon", $icon,
    "--add-data", $webData,
    "--add-data", $assetData,
    "--hidden-import", "qrcode",
    "--hidden-import", "cryptography",
    "--collect-submodules", "qrcode",
    "--exclude-module", "tkinter",
    "--paths", $root,
    "--distpath", $distDir,
    "--workpath", (Join-Path $buildDir "pyinstaller-gui"),
    "--specpath", (Join-Path $buildDir "spec-gui"),
    (Join-Path $root "run_gui.py")
)
& python -m PyInstaller @args
if ($LASTEXITCODE -ne 0) { throw "GUI build failed ($LASTEXITCODE)" }

Copy-Item (Join-Path $distDir "Aster.exe") (Join-Path $root "Aster.exe") -Force

$guiSize = [math]::Round((Get-Item (Join-Path $root "Aster.exe")).Length / 1MB, 1)
Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host "  $root\Aster.exe     ($guiSize MB)  GUI"
