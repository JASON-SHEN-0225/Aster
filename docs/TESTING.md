# 测试记录（Aster 2.0）

测试环境：Windows 11 专业版 10.0.26300、Python 3.10.6、Node 24、PySide6 6.12、Microsoft Edge（Puppeteer 无头驱动，390×844 手机视口）。

## 1. 自动化端到端测试

```powershell
python -m unittest tests.test_e2e -v
```

结果：**10/10 通过，约 12 秒**。

| 用例 | 覆盖点 | 结果 |
|---|---|---|
| `test_file_text_roundtrip` | 文件 + 文本、SHA-256、历史、剪贴板记录 | 通过 |
| `test_folder_dedup_and_empty` | 文件夹相对路径、同名去重、零字节文件 | 通过 |
| `test_resume_from_offset` | 只传一半后按 offset 续传、完整性 | 通过 |
| `test_reject_then_pin` | 手动拒绝、错误 PIN、正确 PIN + 手动接受 | 通过 |
| `test_web_pair_upload_and_offer_download` | 配对码、手机上传、offer、Range 下载 | 通过 |
| `test_discovery_announce` | UDP announce 发现 | 通过 |
| `test_peer_hello_and_history` | hello 手动连接、历史 | 通过 |
| `test_text_only_auto_complete` | 纯文本自动完成 | 通过 |
| `test_https_web_and_peer_transfer` | HTTPS ping/静态页、网页 HTTPS 偏好、HTTPS 对等传输 | 通过 |

另做过端口冲突验证：同一端口第二个 `AsterNode` 会明确报“端口被占用”，不会静默抢占。

## 2. 手机网页真实浏览器测试

启动 `Aster.exe`（或 `python run_gui.py`）后，用 Puppeteer + Edge 在 **390×844、2x DPR、移动/触屏模式** 下执行：

1. 带 `?pair=xxxxxx` 打开页面，自动完成配对；
2. 手机发送文本，电脑剪贴板收到并写入历史；
3. 选择 6 MB 文件，限速 1.5 MB/s 上传，观察进度；
4. 服务端落盘并比对 SHA-256；
5. 切换浅色/深色主题、打开设置抽屉、打开历史抽屉；
6. 打开 HTTPS 开关 → 跳转到 HTTPS 端口（自签名证书警告由用户接受）→ 自动重新配对。

结果：

- 无 `console error`，无失败请求；
- 6 MB 上传 SHA-256 一致：
  `2fb40c0ef3808743b2310c83764ed5588f32132f0c845087ac78945e0ade5705`
- 进度、速度、完成态、历史正确渲染；
- 新配色、首页星轨动画、HTTPS 开关均可见；
- 截图见 `docs/screenshots/mobile-*.png`。

## 3. 电脑 → 手机 offer 测试

用 Python 启动真实 `AsterNode`，再用 Puppeteer 打开网页配对；电脑端调用 `send_to_web` 推文件，手机网页：

1. 出现「待你接收」卡片；
2. 点「接收文件」；
3. 点「保存」，浏览器下载；
4. 下载文件 SHA-256 与源文件一致，offer 状态变为 `completed`。

结果：**通过**，无控制台错误。

## 4. GUI 离屏 / 实际窗口测试

- Qt offscreen 实例化 + 截图：发送页、传输页、历史页、设置页、浅/深主题；
- 实际 `Aster.exe` 启动：窗口标题 `Aster · 星流`、系统托盘、端口 48160/48161 监听；
- GUI E2E：
  - 设备卡片识别第二台电脑；
  - 选择文件 → 目标 → 发送，接收端落盘；
  - 第二台电脑向 GUI 发文件，GUI 弹出接收确认并接受，文件落盘；
  - 关闭窗口后进程仍驻留托盘（未退出）。
- 截图见 `docs/screenshots/gui-*.png`。

## 5. 桌面端打包验收

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

- `Aster.exe`：46 MB，窗口 GUI（无控制台），PySide6 单文件。
- 启动后 HTTP / HTTPS 同时监听，窗口正常渲染。
- 资源管理器右键注册、预传输队列、单实例冷启动入队均已实测。
- 安装包通过 `installer\build-installer.ps1` 重打，包含最新 exe、右键菜单和防火墙规则。

## 6. 大文件测速

1 GiB / 4 GiB，loopback，均做 SHA-256：

| 模式 | 大小 | 耗时 | 吞吐 |
|---|---:|---:|---:|
| HTTP | 1 GiB | 1.31 s | 782.9 MiB/s |
| HTTP | 4 GiB | 5.75 s | 711.8 MiB/s |
| HTTPS | 1 GiB | 2.15 s | 475.6 MiB/s |
| HTTPS | 4 GiB | 8.74 s | 468.4 MiB/s |

结论：HTTPS 不会提速，本次慢约 34–39%。详见 `docs/BENCHMARK.md`。

## 7. 已知限制

1. **防火墙规则需要管理员权限**：安装包会自动添加；免安装版首次打开 GUI 后，在「设置 → 配置 Windows 防火墙」里授权。规则包含 TCP 47820/47821、UDP 47820。
2. **HTTP + PWA 限制**：局域网 `http://IP:47820` 不是安全上下文，浏览器会跳过 Service Worker 和完整 PWA 安装；「添加到主屏幕」只是快捷方式。页面功能不受影响。
3. **HTTPS 自签名**：手机首次访问会提示“连接不是专用连接”，需要点「高级 → 继续访问」。证书不做 CA 校验。
4. **APK**：已生成 debug/release APK；构建步骤见 `docs/ANDROID.md`。
5. **手机端上传不做浏览器端全文件 SHA**：只做长度校验；电脑端对等传输有 SHA-256。
6. **大文件测速是 loopback 上限**：真实 Wi-Fi 受路由器/频段/AP 隔离影响会低很多。
7. **手机端视觉**：已切换为 LocalSend 风格布局，配色与桌面端统一。

## 8. 截图

| 页面 | 文件 |
|---|---|
| GUI 实际窗口 | `docs/screenshots/gui-window.png` |
| GUI 发送 | `docs/screenshots/gui-home.png` |
| GUI 设备选择 | `docs/screenshots/gui-devices.png` |
| GUI 设置 | `docs/screenshots/gui-settings.png` |
| GUI 深色 | `docs/screenshots/gui-dark.png` |
| 手机首页 | `docs/screenshots/mobile-home.png` |
| 手机上传 | `docs/screenshots/mobile-uploading.png` |
| 手机设置 | `docs/screenshots/mobile-settings.png` |
| 电脑发来 | `docs/screenshots/mobile-offer.png` |
| 手机深色 | `docs/screenshots/mobile-dark.png` |
| 手机接收页 | `docs/screenshots/mobile-receive.png` |
| 下载取消 | `tests/test_e2e.py::test_web_offer_cancel_download` |
| 手机文本页 | `docs/screenshots/mobile-text.png` |
| 下载进度 | `docs/screenshots/mobile-offer-progress.png` |
| LocalSend 风格设计稿 | `docs/design/mobile-localsend-design.png` |
