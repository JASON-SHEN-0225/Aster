# Android APK（Aster 2.0.0）

## 现在有 APK 了

Aster 2.0.0 的 Android 端是一个**原生 Kotlin + WebView 壳**，不是 TWA，也不是 Capacitor 内嵌网页工程。APK 本身不实现传输协议，也不带本地后端；它负责连接电脑、扫码、加载电脑托管的手机网页，以及补齐 WebView 不擅长的原生能力（文件选择、下载到系统 Downloads、自签名 HTTPS 证书确认、返回键、系统浏览器跳转）。

电脑端协议、GUI、网页都没有改；`aster/webui/` 仍然由电脑托管。APK 与网页同源访问，**不需要新增 CORS**。

| 项 | 值 |
|---|---|
| 包名 | `com.aster.app` |
| 应用名 | Aster 星流 |
| versionName / versionCode | `2.0.0` / `20000` |
| minSdk / targetSdk / compileSdk | 26 / 35 / 35 |
| 架构 | 原生 Kotlin + Android WebView |
| 扫码 | ZXing embedded（`com.journeyapps:zxing-android-embedded:4.3.0`） |
| release 签名 | 新生成的 `aster-release.jks`，4096-bit RSA / PKCS12 |
| 构建验证 | `aapt dump badging`、`apksigner verify`、18 个 JVM 单元测试、Android lint、桌面端 10 项 e2e |
| 真机验证 | **未做真机验证**（本机没有连接 Android 设备，也没有硬件加速模拟器） |

### 交付物

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| [`android/dist/Aster-2.0.0-debug.apk`](../android/dist/Aster-2.0.0-debug.apk) | 3,064,515 B（2.92 MiB） | `9824FF123AE52061301A84095838C0446EC6D8747304A82E358AE8FF4C37E05A` |
| [`android/dist/Aster-2.0.0-release.apk`](../android/dist/Aster-2.0.0-release.apk) | 2,467,408 B（2.35 MiB） | `17CF2F63663A8A602F4C70A7A0BF8E26C44370C29D3D4B678691C7F5F2CF3693` |

- debug 使用 Android Debug 证书；release 使用新 keystore。两者包名相同但签名不同，**不能直接互装**，切换前要卸载。
- release 没有启用 R8 混淆（`isMinifyEnabled = false`），目的是在没有真机回归的前提下降低运行时风险；APK 仍然只有 2.35 MiB。
- keystore 与密码文件都在 `.gitignore` 里，不会提交。

构建日志、清单、签名、lint 和测试输出：

- [`android/build-logs/environment.txt`](../android/build-logs/environment.txt)
- [`android/build-logs/assembleDebug.log`](../android/build-logs/assembleDebug.log)
- [`android/build-logs/assembleRelease.log`](../android/build-logs/assembleRelease.log)
- [`android/build-logs/aapt-debug.txt`](../android/build-logs/aapt-debug.txt)
- [`android/build-logs/aapt-release.txt`](../android/build-logs/aapt-release.txt)
- [`android/build-logs/apksigner-debug.txt`](../android/build-logs/apksigner-debug.txt)
- [`android/build-logs/apksigner-release.txt`](../android/build-logs/apksigner-release.txt)
- [`android/build-logs/verify.log`](../android/build-logs/verify.log)
- [`android/build-logs/zipalign-debug.txt`](../android/build-logs/zipalign-debug.txt)
- [`android/build-logs/zipalign-release.txt`](../android/build-logs/zipalign-release.txt)
- [`android/build-logs/manifest-release.xml`](../android/build-logs/manifest-release.xml)
- [`android/build-logs/adb-devices.txt`](../android/build-logs/adb-devices.txt)
- [`android/build-logs/sdk-packages.txt`](../android/build-logs/sdk-packages.txt)
- [`android/build-logs/lint-results.txt`](../android/build-logs/lint-results.txt)
- [`android/build-logs/desktop-e2e.log`](../android/build-logs/desktop-e2e.log)

## 本次构建的变更

- **启动扫码优先**：不再在启动时自动加载上次网页；启动后停在连接页并自动调起扫码页，取消扫码后留在连接页。上次地址仍会预填，点「连接」才进入网页。
- **扫码按钮图标对齐**：从 `Button` 的 `drawableStart` 改为独立的 `ImageView + TextView` 水平布局，图标 20dp、文本 `includeFontPadding=false`，图标与文字垂直居中。
- **适配新版网页的自动下载**：网页点「接收」后会连续触发多个 `<a download>`；HTTP 仍走 `DownloadManager`，HTTPS 自签名改为前台服务队列逐个下载，避免多文件时只保存第一个或互相中断。

## APK 做了什么

### 1. 启动：扫码优先

- 每次启动先停在连接页，并自动调起扫码页（第一次会请求相机权限）；取消扫码或拒绝权限后留在连接页。
- 不再自动连接上次地址；上次的 `host + port + 协议` 仍会预填到连接页，点「连接」才进入网页。
- 输入 `电脑 IP`、`IP:端口`、`主机名:端口` 或完整 URL；省略端口时默认 `47820`。
- `HTTPS` 开关默认关闭；打开后默认端口显示 `47821`，输入框里如果是默认端口会自动在 `47820 ↔ 47821` 之间切换。
- 地址保存在 `SharedPreferences`（`aster_shell`：`last_host` / `last_port` / `last_https`），只用于预填，不再在启动时自动加载网页。
- 连接页只保留状态、IP、端口信息，没有营销式说明小字。
- 从桌面图标再次打开（`onNewIntent`）也会回到连接页并重新进入扫码，避免停在旧网页。

### 2. 扫码

- 启动后自动调起 ZXing 竖屏扫码页；也可以随时点连接页的「扫码」按钮。
- 支持 `http://IP:47820/?pair=xxxxxx`，也支持电脑优先 HTTPS 时的 `https://IP:47821/?pair=xxxxxx`。
- 扫码成功后自动填地址、同步 HTTPS 开关，并带着 `?pair=` 直接连接；配对码由网页完成配对，壳不额外保存配对码。
- 手动输入地址同样可以进入网页的配对页输入 6 位配对码。
- 取消扫码后停在连接页，可再次扫码或手动连接；不会自动跳到网页。
- 连接页的「扫码」按钮用独立的水平布局（20dp 图标 + 文本，`includeFontPadding=false`），图标与文字垂直居中，避免 `drawableStart` 在中文下偏高/偏低。

### 3. WebView

- 启用 JavaScript、DOM storage、Content Access、多窗口和真实 UA；关闭缩放与文件访问。
- `android:usesCleartextTraffic="true"` + `network_security_config` 放行局域网明文 HTTP（Android 9+ 必需）。
- 加载 `http(s)://电脑:端口/`，网页保持浅色/深色、星轨、配对、上传、下载、文本、offer、HTTPS 开关全部原样。
- 顶部 3dp 加载进度条；主框架 15 秒无响应会 `stopLoading` 并显示超时页。
- WebView 错误、HTTP 4xx/5xx 都有中文状态页：地址、错误码、重试、换地址。
- 网页主题变化时轮询 `html[data-theme]` 与 body 背景色，同步状态栏/导航栏颜色与图标明暗；连接页固定 Aster 深色品牌。

### 4. 上传

- `WebChromeClient.onShowFileChooser` 使用 `ACTION_OPEN_DOCUMENT`，支持 `MODE_OPEN_MULTIPLE` 多选，返回 `content://` URI。
- 网页本身用 raw XHR 逐文件串行上传并支持 offset 断点，壳不需要 FormData 或 multipart。
- 文件夹选择：网页的「发送文件夹」使用 `<input type="file" webkitdirectory>`；Android WebView 不支持这个属性，点它通常退化为普通多选。壳对 WebView 回传的目录模式（公开常量 `MODE_OPEN_FOLDER` 的值 `2`，compileSdk 35 的 `android.jar` 尚未公开）做 best-effort：用系统目录选择器递归枚举最多 2000 个文件、24 层目录，返回文件 URI。**WebView 不会保留 `webkitRelativePath`，所以文件夹上传到电脑后会变成扁平文件名。**
- 这条限制是 WebView 的，不是 Aster 协议限制；桌面浏览器上传文件夹仍保留相对路径。

### 5. 下载

- 新版手机网页在点「接收」后会自动触发下载，不再需要第二次点「保存」；它对每个文件程序化点击同源 `<a download>`，壳的 `DownloadListener` 接住完整 URL。
- `WebView.setDownloadListener` 拿到完整 `http(s)` URL、UA、Content-Disposition、MIME。
- 文件名优先解析 `filename*=UTF-8''...`（RFC 5987），再退回 `filename="..."` 和 URL 猜测；会清洗路径与非法字符。电脑端下载响应里的 ASCII 回退名会丢中文，这一步是必需的。
- **HTTP 下载**：交给 `DownloadManager`，保存到系统 Downloads 下的 `Aster/`，使用系统下载通知；Android 10+ 不需要存储权限，Android 8/9 会请求 `WRITE_EXTERNAL_STORAGE`。
- **HTTPS 自签名下载**：`DownloadManager` 没有自定义 TrustManager API，会拒绝 Aster 自签名证书。壳改用前台服务 `DownloadService`：使用已确认证书的 SHA-256 做 TLS pinning，流式写入 `MediaStore.Downloads` 的 `Downloads/Aster`（Android 10+）或公共 Downloads（Android 8/9），并显示进度通知。
- 网页可能一次自动触发多个文件：HTTP 由 `DownloadManager` 各自入队；HTTPS 由 `DownloadService` 单线程队列按顺序下载，前一个完成后继续下一个，不会因为「已有下载」丢掉后面的文件。
- 同名文件会自动加 ` (1)`、` (2)` 后缀；文件最终落在系统「下载」里，不在应用私有目录。

### 6. HTTPS 自签名证书

- `onReceivedSslError` 不会静默 `proceed()`。
- 首次出现某个 `host:port` 的证书时弹原生确认框，显示地址、颁发者、SHA-256；选「继续」后把 DER 与指纹记在 `SharedPreferences`，之后该证书的同一 host/port 自动放行；选「取消」显示 HTTPS 错误页。
- 证书按请求回调（CSS/JS/图标/SSE 都会触发），壳会合并同一次确认的多个 handler，避免弹框风暴。
- 电脑换 IP/重新生成证书后指纹变化，会重新确认；不会无限期信任旧证书。
- 只有目标电脑的证书会被记住；其他外部 HTTPS 仍走系统信任。

### 7. 返回键、外部链接、键盘和刘海

- 返回键：有 WebView 历史就后退；否则检查网页是否打开了设置浮层（`body.sheet-open`），是则注入 Escape 关闭；再否则回到连接页；连接页再按返回退出。
- 外部链接交给系统浏览器；Aster 电脑的内网地址（同一 host，或内网 IP + Aster 常用端口 / 带 6 位 `pair` 的切换地址）留在 WebView 内，保证网页里的 HTTP/HTTPS 切换不会被踢到浏览器。
- `target=_blank` 通过 `onCreateWindow` 捕获；内部链接留在当前 WebView，外部链接交给浏览器。
- 使用 edge-to-edge + WindowInsets：状态栏/导航栏/刘海/输入法都有 padding，WebView 不会钻到系统栏下面。
- 启动页使用 Aster 深色背景 + 星芒图标；启动图标复用现有星流 SVG 生成的透明 PNG。

## 工程结构

```text
android/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── gradle/wrapper/                     # Gradle 8.9 wrapper
├── gradlew / gradlew.bat
├── local.properties                    # 本机 SDK 路径，gitignore
├── keystore.properties                 # 密码，gitignore
├── keystore/aster-release.jks          # 签名，gitignore
├── app/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml
│       │   ├── java/com/aster/app/
│       │   │   ├── MainActivity.kt      # 连接页/WebView/上传/下载/证书/导航/Insets
│       │   │   ├── Address.kt           # 地址解析、Endpoint、pair 提取
│       │   │   ├── Prefs.kt             # 地址与证书 pin
│       │   │   ├── DownloadNames.kt     # filename*、清洗、去重、MediaStore
│       │   │   ├── DownloadService.kt   # HTTPS 自签名下载前台服务
│       │   │   ├── CertUtil.kt          # DER/指纹/颁发者
│       │   │   └── QrScanActivity.kt    # ZXing 竖屏扫码
│       │   └── res/
│       │       ├── layout/activity_main.xml
│       │       ├── drawable*/           # 星流 logo、按钮、输入框、图标
│       │       ├── mipmap*/             # 自适应启动图标
│       │       ├── values/              # 品牌色、字符串、主题
│       │       ├── values-v31/themes.xml# Android 12+ splash
│       │       └── xml/network_security_config.xml
│       └── test/java/com/aster/app/     # 18 个 JVM 单元测试
├── tools/icon-*.html                    # 透明星芒 PNG 生成源
├── dist/                                # 两个 APK（gitignore）
└── build-logs/                          # 构建/验证日志（gitignore）
```

## 环境安装（Windows 11）

本节记录本机实际使用的版本；换机器时按相同版本装即可。**不要求 Android Studio**，也不做 iOS。

| 组件 | 版本 / 路径 |
|---|---|
| JDK | Temurin 17.0.21，`D:\Android\jdk-17` |
| Android cmdline-tools | 12.0（build 11076708），`D:\Android\sdk\cmdline-tools\latest` |
| Android platform | `platforms;android-35`（rev 2） |
| Build tools | `build-tools;35.0.0`；AGP 还会自动装 `34.0.0` |
| Platform tools / adb | 37.0.3 |
| Gradle | 8.9（wrapper），`D:\Android\gradle-8.9` 仅用于生成 wrapper |
| AGP / Kotlin | 8.7.3 / 2.0.21 |
| 磁盘 | SDK + Gradle 缓存约 4–5 GB |

### 1. JDK 17

下载 Temurin 17（官方 Adoptium 或镜像），解压到 `D:\Android\jdk-17`，确认：

```powershell
& 'D:\Android\jdk-17\bin\java.exe' -version
# openjdk version "17.0.21" ...
```

设置用户环境变量（不需要管理员）：

```powershell
setx JAVA_HOME "D:\Android\jdk-17"
```

### 2. Android command-line tools

下载 `commandlinetools-win-*.zip`，解压后把 `cmdline-tools` 目录整理成：

```text
D:\Android\sdk\cmdline-tools\latest\bin\sdkmanager.bat
```

然后接受许可并安装：

```powershell
$env:JAVA_HOME = "D:\Android\jdk-17"
$env:ANDROID_HOME = "D:\Android\sdk"
$env:ANDROID_SDK_ROOT = "D:\Android\sdk"

& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" --licenses
& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" `
    "platform-tools" "platforms;android-35" "build-tools;35.0.0"
```

> 本次机器上 `sdkmanager --licenses` 用 PowerShell 管道喂 `y` 会拿到 EOF；改用 `cmd.exe /c "...sdkmanager.bat --licenses < y.txt"` 或交互输入即可。

设置：

```powershell
setx ANDROID_HOME "D:\Android\sdk"
setx ANDROID_SDK_ROOT "D:\Android\sdk"
```

### 3. Gradle

工程已带 Gradle 8.9 wrapper，不需要单独安装 Gradle。

- `android/gradle/wrapper/gradle-wrapper.properties` 默认使用华为云镜像，并带官方 SHA-256 校验：

```properties
distributionUrl=https\://mirrors.huaweicloud.com/gradle/gradle-8.9-bin.zip
distributionSha256Sum=d725d707bfabd4dfdc958c624003b3c80accc03f7037b5122c4b1d0ef15cecab
```

- 如果所在网络能直连 Gradle 官方源，也可以改回：

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.9-bin.zip
```

首次构建会下载 129.8 MB 的分发包；若公司网络限制，可提前把 `gradle-8.9-bin.zip` 放到本地，把 `distributionUrl` 改成 `file:///.../gradle-8.9-bin.zip`。

### 4. 指向 SDK

`android/local.properties`（已在 `.gitignore` 中）：

```properties
sdk.dir=D\:\\Android\\sdk
```

也可以用 `ANDROID_HOME` 环境变量代替。`local.properties` 不要提交。

### 5. 依赖下载

Gradle 的 `google()` 实际走 `https://dl.google.com/dl/android/maven2/`，不受 `maven.google.com` 直连失败影响；`mavenCentral()` 和 `gradlePluginPortal()` 需可访问。AGP/Kotlin/AndroidX/ZXing 都在这三个源里。

## 构建

```powershell
cd android   # 在仓库根目录执行

$env:JAVA_HOME = "D:\Android\jdk-17"
$env:ANDROID_HOME = "D:\Android\sdk"
$env:ANDROID_SDK_ROOT = "D:\Android\sdk"

.\gradlew.bat testDebugUnitTest
.\gradlew.bat assembleDebug
.\gradlew.bat assembleRelease
```

产物：

```text
app/build/outputs/apk/debug/app-debug.apk
app/build/outputs/apk/release/app-release.apk
```

复制成要求的名字：

```powershell
New-Item -ItemType Directory -Force dist | Out-Null
Copy-Item app\build\outputs\apk\debug\app-debug.apk `
    dist\Aster-2.0.0-debug.apk -Force
Copy-Item app\build\outputs\apk\release\app-release.apk `
    dist\Aster-2.0.0-release.apk -Force
```

### 签名

release 签名读取 `android/keystore.properties`（**不要提交**，仓库只保留模板 [`android/keystore.properties.example`](../android/keystore.properties.example)）：

```properties
storeFile=keystore/aster-release.jks
storePassword=<密码>
keyAlias=aster
keyPassword=<密码>
```

keystore 生成方式（本次已生成，下面的命令只是复现说明）：

```powershell
& 'D:\Android\jdk-17\bin\keytool.exe' -genkeypair -v `
  -keystore keystore\aster-release.jks -alias aster `
  -keyalg RSA -keysize 4096 -validity 10000 -storetype PKCS12 `
  -storepass <密码> -keypass <密码> `
  -dname "CN=Aster, OU=Aster Android, O=Aster, L=Local, ST=Local, C=CN"
```

release 证书 SHA-256：

```text
C8:14:01:C6:67:9E:84:00:34:4C:2F:4D:A2:36:F1:E0:EC:AD:B2:26:E9:E5:9C:1D:95:A9:12:B4:13:AC:1E:1C
```

`keystore/`、`keystore.properties`、`local.properties`、`dist/`、`build-logs/`、`.gradle/`、`app/build/` 都在 `.gitignore` 中。

## 安装

### adb

```powershell
# 在 android/ 目录执行
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r `
  dist\Aster-2.0.0-release.apk
```

或：

```powershell
adb install -r dist\Aster-2.0.0-debug.apk
```

### 手机端

1. 把 `Aster-2.0.0-release.apk` 拷到手机（USB / 网盘 / 微信文件传输均可）。
2. 在文件管理器里点开，允许「安装未知应用」。
3. 首次打开会请求相机权限并直接进入扫码页；扫电脑上的二维码即可连接。电脑和手机必须在同一 Wi-Fi。
4. 取消扫码会停在连接页，可手动输入电脑 IP、点「连接」，再在网页里输入 6 位配对码。

### 电脑端

1. 运行 `Aster.exe`。
2. 首次使用在 Aster「设置 → 配置 Windows 防火墙」里授权，或使用安装包自动添加 TCP 47820/47821、UDP 47820。
3. GUI 左下角「手机网页 → 二维码」。
4. 如果手机打不开，先用 GUI 显示的 IP/端口确认，再用手机浏览器访问 `http://IP:47820/` 排除网络/防火墙问题。

### debug/release 互装

两者包名都是 `com.aster.app`，但 debug 用 Android Debug 证书、release 用 `aster-release.jks`。直接覆盖会报：

```text
INSTALL_FAILED_UPDATE_INCOMPATIBLE
```

先卸载旧版本：

```powershell
adb uninstall com.aster.app
```

注意：卸载会清掉 WebView 的 localStorage，配对 token 会丢失，需要重新配对。

## 使用与行为

### 连接页

- 地址支持 `192.168.1.5`、`192.168.1.5:47820`、`aster-pc:47820`、`https://192.168.1.5:47821/?pair=123456`、`[fe80::1]:47820`。
- 端口省略：HTTP 默认 `47820`，HTTPS 默认 `47821`。
- 启动自动进扫码；取消扫码/拒绝相机权限后停在连接页。启动时只预填上次地址，**不自动连接网页**；点「连接」才加载。
- 保存的是 `host + port + 协议`，不保存 `pair`；连接后网页用 localStorage 里的 token 自动重连；电脑重启后 token 失效，网页会回到配对页。
- 上次地址会保留；连接失败时错误页有「重试」「换地址」。
- 电脑端更新 exe 后不需要重装 APK：重新扫码，或在连接页改 IP/端口即可。

### 配对

- 配对在网页里完成，壳不参与配对协议。
- 网页 token 存在 WebView 的 localStorage；壳不清 WebView 数据。
- 电脑进程重启、网页离线超过约 1 小时、或桌面轮换配对码后，旧 token 可能失效；网页会显示配对页。
- 扫码带 `?pair=` 时会自动配对；HTTPS 网页和 HTTP 网页是不同 origin，localStorage 不共享，网页的 HTTPS 开关会带 `?pair=` 重新配一次。

### 上传

- 点网页里的「发送文件」→ 系统文件选择器 → 可多选。
- 发送文件夹在 Android WebView 上会退化为多选文件；文件会平铺到电脑的接收目录。
- 上传中断后网页会尝试用 offset 续传（最多 3 次重试）。

### 下载

- 电脑发来文件后，在网页里点「接收」。新版网页会自动开始下载（可能多个文件），不需要再点一次「保存」。
- HTTP：系统 `DownloadManager` 下载到 `下载/Aster/`，通知栏可见；Android 10+ 无存储权限要求。
- HTTPS：前台服务下载，多个文件按队列依次下载，同样到 `下载/Aster/`，通知栏显示进度；Android 13+ 建议允许通知，否则只有完成后的 Toast。
- 文件名中的中文来自 `filename*=UTF-8''...`，不再使用 ASCII 回退名。

### 返回键

1. WebView 有历史 → 后退。
2. 网页设置浮层打开 → 注入 Escape 关闭浮层。
3. 否则 → 回到连接页（网页仍保留在后台，不会主动 reload）。
4. 连接页再按返回 → 退出应用。

### 外部链接

- Aster 电脑的内网地址、Aster 常用端口、带 6 位 `pair` 的切换地址留在 WebView。
- 其他 http(s)、`intent:`、`mailto:` 等链接交给系统浏览器/系统应用；打不开时 Toast「没有可打开该链接的应用」。

## HTTP / HTTPS 限制

- **HTTP 是明文**。放行明文只是为了局域网 IP 不固定的 Aster，请只在可信 Wi-Fi 使用，不要把 47820/47821 映射到公网。
- **HTTPS 是自签名证书**，只加密，不做 CA 身份认证。首次连接会出现 Aster 原生的证书确认框（地址、颁发者、SHA-256），点「继续」后按 host/port 记住该证书；换 IP/换证书会重新确认。
- **不要全局信任所有证书**：本 APK 只对确认过的证书做 pinning，并在取消时显示错误页。
- `DownloadManager` 不信任自签名证书，所以 HTTPS 下载走壳内的 `DownloadService`；HTTP 下载仍使用 `DownloadManager`。
- HTTP 不是安全上下文：网页的剪贴板 API 会降级到 `execCommand`，Service Worker 与完整 PWA 安装会被跳过，`beforeinstallprompt` 在 WebView 中也不会触发；这些都不影响配对、上传、下载、文本与 offer。
- HTTPS 不会更快；Aster 自己的测速显示 HTTPS 比 HTTP 慢约 34–39%（[BENCHMARK.md](BENCHMARK.md)）。需要加密时再开 HTTPS。
- WebView 只对当前主框架与同级资源做证书确认；外部 HTTPS 资源仍走系统信任。

## 验证结果

### 构建与签名

- `gradlew assembleDebug`：成功。
- `gradlew assembleRelease`：成功，release 已签名。
- `aapt dump badging`：

```text
package: name='com.aster.app' versionCode='20000' versionName='2.0.0' compileSdkVersion='35'
sdkVersion:'26'
targetSdkVersion:'35'
application: label='Aster 星流'
launchable-activity: name='com.aster.app.MainActivity'
```

- `apksigner verify --verbose --print-certs`：两个 APK 均 `Verifies`，v2 签名通过。
  - debug：`CN=Android Debug`，证书 SHA-256 `AF:BB:4C:5E:7F:77:93:69:10:37:5C:6B:09:1C:AE:5A:CA:57:C8:96:FA:35:70:0E:71:0C:BA:E3:DD:B1:B7:2B`。
  - release：`CN=Aster, OU=Aster Android, O=Aster, L=Local, ST=Local, C=CN`，证书 SHA-256 `C8:14:01:C6:67:9E:84:00:34:4C:2F:4D:A2:36:F1:E0:EC:AD:B2:26:E9:E5:9C:1D:95:A9:12:B4:13:AC:1E:1C`。
- `zipalign -c -v 4`：两个 APK 均为 `Verification succesful`。

### 单元测试与 lint

- 18/18 JVM 单元测试通过：
  - `AddressParserTest` 10 个：默认端口、HTTPS、显式端口、IPv6、主机名、pair 校验、非法地址、路径/查询清洗。
  - `DownloadNamesTest` 8 个：RFC 5987 中文文件名、引号/无引号 filename、非法头、路径清洗、Unicode、同名后缀、超长扩展名。
- `gradlew lintDebug`：**0 errors, 24 warnings**。警告集中在「允许明文 HTTP」「自定义 TrustManager（这是证书 pinning 的实现）」「扫码页锁定竖屏」「allowBackup 在 Android 12+ 的备份提示」等已知设计取舍，详见 [`lint-results.txt`](../android/build-logs/lint-results.txt)。

### 桌面端回归

`python -m unittest tests.test_e2e -v`：**10/10 OK**，包含 HTTP 网页配对 + 手机上传 + offer Range 下载、HTTPS 网页、优先 HTTPS 对等传输、断点续传等。日志：[`desktop-e2e.log`](../android/build-logs/desktop-e2e.log)。

### 未做真机验证

- `adb devices` 没有连接设备（见 [`adb-devices.txt`](../android/build-logs/adb-devices.txt)）。
- 本机没有安装 Android 模拟器；`HypervisorPresent=False`，没有可用的 WHPX/HAXM 硬件加速，不采用纯软件模拟。
- 因此以下项目**没有在真实 Android 设备上执行**：
  - APK 安装/启动、启动自动进扫码、相机权限；
  - 连接页、扫码图标对齐的视觉效果；
  - WebView 加载电脑网页与配对；
  - 文件选择器多选、真实上传；
  - HTTP/HTTPS 下载到系统 Downloads、网页连续自动下载多个文件；
  - 返回键、系统浏览器跳转、Android 13/14/15 的通知与前台服务行为。
- 已完成的验证是：编译、链接、资源打包、签名、清单、JVM 逻辑测试、lint、桌面端回归。**“未做真机验证”是本次交付的明确限制，不是隐含通过。** 本次启动扫码优先、扫码图标布局、下载队列的改动没有真机回归。

## 已知问题与限制

1. **未做真机验证**（见上）。
2. **文件夹上传**：Android WebView 不支持 `webkitdirectory`，网页的文件夹按钮退化为多文件选择；即使走壳的目录枚举，`webkitRelativePath` 也丢失，电脑端看到的是扁平文件。桌面浏览器不受影响。
3. **WebView 版本依赖**：功能依赖系统 WebView（Android System WebView / Chrome）。Android 8.0 自带 WebView 较旧时，`?pair=` 自动配对、SSE、文件选择等行为可能与新版本不同；建议在应用商店更新 WebView。
4. **没有后台接收**：页面/进程被系统杀掉后不会收文件；电脑发来的 offer 在桌面端保留约 24 小时，下次打开网页可见。
5. **HTTPS 切换地址由电脑计算**：网页的 HTTPS 开关会跳到电脑 `get_lan_ip()` 算出的 LAN IP，可能和手机输入的 IP 不同（多网卡、VPN、热点）。壳会把内网 IP + Aster 端口、或带 `pair` 的切换地址留在 WebView；若该 IP 不可达，会显示错误页。
6. **HTTPS 下载的前台服务**：Android 14+ 使用 `dataSync` 前台服务；Android 15 对前台服务有 6 小时限制。极大文件建议保持应用在前台。
7. **通知权限**：Android 13+ 首次 HTTPS 下载会请求通知权限；拒绝后仍能下载，但只有完成 Toast，没有进度通知。
8. **同名文件**：HTTP `DownloadManager` 路径由壳查询 MediaStore 去重；如果系统/存储提供方不返回其他应用已下载的同名项，仍可能出现同名覆盖/系统自动改名。文件都在 `下载/Aster/`。
9. **release 未混淆**：`isMinifyEnabled=false`；如果后续启用 R8，需要重新验证 ZXing、下载服务和 WebView 反射相关代码。
10. **debug/release 签名不同**：不能互相覆盖安装；卸载会清 WebView localStorage，需要重新配对。
11. **端口/防火墙**：电脑端仍需放行 TCP 47820/47821、UDP 47820；手机和电脑必须同一 Wi-Fi，路由器关闭 AP 隔离。
12. **不做 iOS**：只有 Android APK。
13. **没有 Play Store 上架配置**：没有 AAB、资产链接、商店签名；APK 是侧载构建。
14. **证书确认是 TOFU**：只在首次确认时比较 SHA-256；不提供 CA 链验证，也不安装 CA 到系统。
15. **桌面端审计发现（未改桌面端）**：当桌面关闭「网页配对」时，`server.py` 的 `web_pair` 分支会跳过配对码校验；这是桌面端既有行为，本次 APK 不依赖它，也没有改桌面端协议/代码。
16. **壳内 HTTPS 下载串行队列**：多个文件会自动依次下载（不是并行），全部完成后服务才停止；不会因为前一个文件正在下载而丢掉后一个。HTTP 下载由系统 `DownloadManager` 处理，不受此限制。
17. **没有做 Aster 身份预检**：壳直接加载输入的地址；如果端口指向另一个 HTTP 服务，会显示那个服务的页面，而不会提示「这不是 Aster」。请核对 IP/端口（桌面端 GUI 显示的 IP、`/api/v1/ping` 可验证）。

## 为什么不是 TWA / Capacitor

- **TWA**：需要受信任的 HTTPS + Digital Asset Links 才能隐藏地址栏；Aster 是自签名证书 + 动态局域网 IP，正好不适合。强行用会显示地址栏，且证书/资产链接仍然过不了。
- **Capacitor**：仍然是 WebView，文件选择、下载、自签名证书、返回键这些原生适配一样要写；还会引入 Node/前端构建层和额外运行时。直接原生 Kotlin 壳依赖更少、APK 更小，也更容易控制 `DownloadManager` 与证书 pinning。
- **PWA 网页**仍然保留：不装 APK 时，手机浏览器扫码即用；APK 只是更完整的入口。

## 常见问题

**构建报 `JAVA_HOME is not set`**
- 当前 PowerShell 会话设置：`$env:JAVA_HOME = "D:\Android\jdk-17"`；或新开终端读取用户环境变量。

**Gradle wrapper 下载失败**
- 默认走华为云镜像；若被限制，改 `distributionUrl` 为能访问的镜像或本地 `file:///.../gradle-8.9-bin.zip`，并保留/更新 `distributionSha256Sum`。

**`sdkmanager` 许可未接受**
- 运行 `sdkmanager --licenses`；本机在 PowerShell 管道下失败时用 `cmd.exe` 重定向输入 `y`。

**手机打不开 `http://IP:47820/`**
- 确认同一 Wi-Fi、电脑 Aster 正在运行、防火墙已放行、路由器未开 AP 隔离；用 GUI 显示的 IP 核对。

**HTTPS 提示证书不受信任**
- 正常。确认地址与 SHA-256 后点「继续」；换 IP 后证书会重新生成，需要再次确认。

**HTTPS 下载失败**
- 确认通知权限；确认下载时手机与电脑仍连通；如果刚换过 IP，先在网页里重新接受一次证书，让壳更新 pin。

**安装报 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`**
- 先 `adb uninstall com.aster.app`，再装；卸载会丢配对 token。

**文件夹上传后没有目录结构**
- 已知 WebView 限制；用桌面浏览器或压缩成 zip 后上传。

---

相关文档：[架构](ARCHITECTURE.md)、[测试](TESTING.md)、[测速](BENCHMARK.md)、[项目 README](../README.md)。
