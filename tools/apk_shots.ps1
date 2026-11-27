# Aster 3.0 APK 真机截图辅助脚本
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools\apk_shots.ps1 -WaitSeconds 600
#   powershell -ExecutionPolicy Bypass -File tools\apk_shots.ps1 -ShareFile "D:\path\demo.pdf"
#
# 需要：adb 在 D:\Android\sdk\platform-tools\adb.exe，手机已开启 USB/无线调试并授权。
# 输出：build\apk-shots\01-connect.png、02-star-frame.png、03-share-text.png、device-info.txt、ui.xml

param(
    [string]$Adb = "D:\Android\sdk\platform-tools\adb.exe",
    [string]$Apk = "D:\\.dsh_localsend\\android\\dist\\Aster-3.0.0-release.apk",
    [string]$OutDir = "D:\\.dsh_localsend\\build\\apk-shots",
    [int]$WaitSeconds = 0,
    [string]$ShareFile = ""
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Adb)) { throw "adb not found: $Adb" }
if (-not (Test-Path $Apk)) { throw "APK not found: $Apk" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Get-Devices {
    $lines = & $Adb devices | Select-Object -Skip 1
    return @($lines | Where-Object { $_ -match "\s+device$" })
}

$deadline = (Get-Date).AddSeconds([Math]::Max(0, $WaitSeconds))
$devices = Get-Devices
while ($devices.Count -eq 0 -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $devices = Get-Devices
}
if ($devices.Count -eq 0) {
    Write-Host "NO_DEVICE: adb devices 为空。请连接手机并授权 USB/无线调试。" -ForegroundColor Yellow
    exit 2
}

$serial = ($devices[0] -split "\s+")[0]
Write-Host "device: $serial" -ForegroundColor Cyan
$model = (& $Adb -s $serial shell getprop ro.product.model).Trim()
$release = (& $Adb -s $serial shell getprop ro.build.version.release).Trim()
$sdk = (& $Adb -s $serial shell getprop ro.build.version.sdk).Trim()
$deviceName = (& $Adb -s $serial shell settings get global device_name).Trim()
$info = @(
    "serial=$serial",
    "model=$model",
    "android=$release (SDK $sdk)",
    "settings_device_name=$deviceName"
)
$info | Set-Content -LiteralPath (Join-Path $OutDir "device-info.txt") -Encoding UTF8
$info | ForEach-Object { Write-Host $_ }

Write-Host "installing APK..." -ForegroundColor Cyan
$install = & $Adb -s $serial install -r $Apk 2>&1
$install | Set-Content -LiteralPath (Join-Path $OutDir "install.txt") -Encoding UTF8
if ($LASTEXITCODE -ne 0 -or ($install -join "`n") -notmatch "Success") {
    Write-Host "INSTALL_FAILED" -ForegroundColor Red
    $install | ForEach-Object { Write-Host $_ }
    exit 3
}

function Save-Shot([string]$Name) {
    $remote = "/sdcard/aster-$Name.png"
    & $Adb -s $serial shell screencap -p $remote | Out-Null
    $local = Join-Path $OutDir $Name
    & $Adb -s $serial pull $remote $local | Out-Null
    & $Adb -s $serial shell rm -f $remote | Out-Null
    Write-Host "shot: $local"
}

function Save-Ui {
    & $Adb -s $serial shell uiautomator dump /sdcard/aster-ui.xml | Out-Null
    & $Adb -s $serial pull /sdcard/aster-ui.xml (Join-Path $OutDir "ui.xml") | Out-Null
    & $Adb -s $serial shell rm -f /sdcard/aster-ui.xml | Out-Null
}

Write-Host "launching connect page..." -ForegroundColor Cyan
& $Adb -s $serial shell am force-stop com.aster.app | Out-Null
& $Adb -s $serial shell monkey -p com.aster.app -c android.intent.category.LAUNCHER 1 | Out-Null
Start-Sleep -Seconds 3
Save-Shot "01-connect.png"
Start-Sleep -Milliseconds 900
Save-Shot "02-star-frame.png"
Save-Ui

Write-Host "text share test..." -ForegroundColor Cyan
$text = "来自微信的分享文本：Aster 3.0 测试"
& $Adb -s $serial shell am start -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT $text | Out-Null
Start-Sleep -Seconds 2
Save-Shot "03-share-text.png"
Save-Ui

if ($ShareFile -and (Test-Path $ShareFile)) {
    Write-Host "file share test..." -ForegroundColor Cyan
    $remoteName = "aster-share-" + [IO.Path]::GetFileName($ShareFile)
    & $Adb -s $serial push $ShareFile "/sdcard/Download/$remoteName" | Out-Null
    # file:// 在部分 ROM 上会被 scoped storage 拦；失败时改用手机相册/微信分享
    & $Adb -s $serial shell am start -a android.intent.action.SEND -t "*/*" --eu android.intent.extra.STREAM "file:///sdcard/Download/$remoteName" | Out-Null
    Start-Sleep -Seconds 3
    Save-Shot "04-share-file.png"
    Save-Ui
}

Write-Host "DONE: $OutDir" -ForegroundColor Green
