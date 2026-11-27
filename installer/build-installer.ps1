# Build Aster Windows installer (Inno Setup 6)
# Usage: powershell -ExecutionPolicy Bypass -File installer\build-installer.ps1
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$root = Split-Path -Parent $here
Set-Location $root

$exe = Join-Path $root "Aster.exe"
if (-not (Test-Path $exe)) { throw "Aster.exe not found. Run build.ps1 first." }

$pf86 = [Environment]::GetFolderPath("ProgramFilesX86")
$pf = [Environment]::GetFolderPath("ProgramFiles")
$local = Join-Path $env:LOCALAPPDATA "Programs"
$candidates = @(
    (Join-Path $pf86 "Inno Setup 6\ISCC.exe"),
    (Join-Path $pf "Inno Setup 6\ISCC.exe"),
    (Join-Path $local "Inno Setup 6\ISCC.exe")
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "ISCC.exe not found. Install Inno Setup 6 first: winget install JRSoftware.InnoSetup"
}

Write-Host "ISCC: $iscc" -ForegroundColor Cyan
& $iscc (Join-Path $here "Aster.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed ($LASTEXITCODE)" }

$setup = Join-Path $here "dist\Aster-Setup-3.0.0.exe"
if (-not (Test-Path $setup)) { throw "Missing output: $setup" }
$item = Get-Item $setup
$hash = Get-FileHash $setup -Algorithm SHA256
$sumFile = Join-Path $here "dist\SHA256SUMS.txt"
Set-Content -LiteralPath $sumFile -Value ($hash.Hash + "  Aster-Setup-3.0.0.exe") -Encoding ASCII

Write-Host ""
Write-Host "Installer built:" -ForegroundColor Green
Write-Host ("  " + $setup)
Write-Host ("  Size    : " + $item.Length + " bytes (" + [math]::Round($item.Length / 1MB, 1) + " MB)")
Write-Host ("  SHA-256 : " + $hash.Hash)
Write-Host ("  Checksum: " + $sumFile)
