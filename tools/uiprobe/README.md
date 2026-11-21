# 浏览器探针（可选）

这两个脚本用于验证手机网页端，不是运行 Aster 的依赖。

前置：

```powershell
cd tools\uiprobe
npm install puppeteer-core
```

本机 Edge 路径在脚本里写死为：

```text
C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
```

## 1. 手机上传/文本/设置

先启动服务并拿到配对码：

```powershell
python -m aster web --port 47880 --dir D:\.dsh_localsend\build\web_dl
```

另一个终端：

```powershell
node tools\uiprobe\probe.js http://127.0.0.1:47880 123456
```

- 会生成 390×844、2x 的截图到 `build/ui-shots/`；
- 会上传 6 MB 文件（默认下载目录 `build/web_dl`）；
- 输出 JSON，包含控制台错误、SHA-256 对比、落盘结果。

## 2. 电脑 → 手机 offer

```powershell
python tools\offer_e2e.py
```

该脚本会启动一个临时 `AsterNode`（47883），再用 `offer_probe.js` 打开网页，电脑端推送文件，手机端接受并下载，最后比对 SHA-256。

注意：这些脚本会创建 `build/` 下的测试数据；`.gitignore` 已忽略。
