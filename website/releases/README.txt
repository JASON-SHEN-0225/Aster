把安装包放在这个目录里，下载按钮就会生效。
==========================================

文件命名（与 assets/js/config.js 保持一致）：

  Aster-Setup-2.0.0.exe          （Windows 安装包，约 48.6 MB）
  Aster.exe                      （免安装 GUI，约 47 MB）
  Aster-2.0.0-release.apk        （Android APK，约 2.4 MB）
  SHA256SUMS.txt                 （可选，页面会自动读取并显示校验值）

源码与版本发布：

  https://github.com/JASON-SHEN-0225/Aster
  https://github.com/JASON-SHEN-0225/Aster/releases

启用方式（二选一）：

1) 文件放在本站 releases/ 目录：
   打开 assets/js/config.js，把 base 改成 "releases/"

2) 文件放在 OSS / CDN 的独立目录：
   把 base 改成绝对地址，例如 "https://dl.asterdrop.cn/"

生成校验值（在存放安装包的目录里执行）：

  Get-FileHash .\Aster-Setup-2.0.0.exe -Algorithm SHA256
  # 按 "<小写哈希>  <文件名>" 的格式写入 SHA256SUMS.txt

注意：
- config.base 留空时，下载按钮显示「即将开放」，不会产生 404。
- 上传大文件建议用 ossutil，控制台网页上传对 50 MB 文件不友好。
- 更换版本号时，同时更新 config.js 的 version / versionLabel / files.name。
