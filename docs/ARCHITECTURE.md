# Aster 2.0 架构

## 总览

```text
┌────────────────── 电脑 A ──────────────────────────────┐
│  GUI (PySide6) ── AsterNode ── ThreadingHTTPServer      │
│                          │        ├─ HTTP 47820       │
│                          │        └─ HTTPS 47821      │
│                          ├─ DiscoveryService (UDP)    │
│                          ├─ HistoryStore / Config     │
│                          └─ TLS 证书 / 网页会话 / SSE  │
└──────────────────┼─────────────────────────────────────┘
                   │  HTTP / HTTPS（JSON + 文件流）
┌──────────────────┼────────────────── 电脑 B ──────────┐
│         DiscoveryService  AsterNode ── PWA 静态页     │
└───────────────────────────────────────────────────────┘
                   │
             手机浏览器（手机网页 / APK WebView）
             扫码 → 配对 → 上传/下载/HTTPS 切换
```

Aster 没有中心服务器。每台电脑都是一个节点，同时监听 HTTP 与 HTTPS；GUI 是唯一桌面前端，内置并托管手机网页。

## 模块

| 模块 | 职责 |
|---|---|
| `aster/gui/` | PySide6 GUI：主窗口、设备卡片、拖拽、接收确认、历史、设置、二维码、托盘 |
| `aster/server.py` | `AsterNode`：HTTP/HTTPS 服务、接收会话、令牌、断点、SHA、网页 API、SSE、发送编排 |
| `aster/client.py` | `PeerClient`：HTTP/HTTPS 请求、上传、完成、取消；`expand_paths` |
| `aster/tls.py` | 自签名证书生成、SAN、TLS 服务端/客户端上下文 |
| `aster/discovery.py` | UDP 多播/广播发现、在线状态、手动探测、主动搜索 |
| `aster/queue.py` | 右键发送的预传输队列（`%APPDATA%\Aster\inbox`） |
| `aster/shellmenu.py` | 当前用户资源管理器右键菜单注册 |
| `aster/single_instance.py` | GUI 单实例互斥体 |
| `aster/config.py` | 配置：端口、HTTPS 偏好、下载目录、PIN、配对码、主题 |
| `aster/history.py` | JSON 历史，线程安全，最多 300 条 |
| `aster/firewall.py` | Windows 防火墙：TCP 47820/47821、UDP 47820 |
| `aster/webui/` | 手机网页：HTML/CSS/原生 JS、manifest、图标；浅/深色、星轨动画、HTTPS 开关 |
| `tools/benchmark.py` | 1 GiB/4 GiB HTTP vs HTTPS 测速 |
| `tests/test_e2e.py` | 真实双节点测试（含 HTTPS） |

## 关键线程

`AsterNode.start()` 后：

- **HTTP 服务线程**：`ThreadingHTTPServer.serve_forever`。
- **HTTPS 服务线程**：同一 handler，socket 用 `ssl.SSLContext` 包装；HTTP/HTTPS 共用节点状态。
- **发现接收/广播/清理线程**：UDP announce/query/bye，在线状态。
- **清理线程**：超时会话、过期 offer、陈旧临时目录、离线网页 token。
- **发送线程**（GUI）：后台执行 `send_to_peer`；GUI 用 QTimer 轮询。
- **SSE 线程**：每个配对网页一个，每秒写一帧完整状态。
- **GUI 主线程**：Qt 事件循环；`QTimer` 每 600ms 拉一次 `node.snapshot()`，接收确认用 `ReceiveDialog.exec()` 阻塞等待用户选择。

所有共享状态由 `AsterNode.lock`（RLock）保护；文件 IO 在锁外执行。

## 双端口与 TLS

```text
启动：
  HTTP server 0.0.0.0:47820
  ensure_cert(data_dir/certs)  # RSA2048、SAN=localhost/主机名/IPs
  HTTPS server 0.0.0.0:47821（失败仅记录，不阻塞 HTTP）

开关 prefer_https：
  只影响默认网页地址/二维码 + 电脑间发送时选 HTTPS
  两个端口始终监听，切换无需重启
```

- 证书 IP 变化会重新生成；`tls_fingerprint` 出现在设备信息和 GUI/网页设置中。
- 手机首次访问 HTTPS 会看到自签名证书警告；点「高级 → 继续访问」。
- `PeerClient` 根据 `prefer_https` + 对端 `https_port` 选择协议。

## 接收流程

```text
POST /transfer/request
  → 校验 PIN / 文件大小 / 磁盘空间
  → 创建 IncomingSession + .part 路径 + 每文件 token
  → 自动接受？是 → active
  → 否 → PendingRequest，等待 GUI 确认框（默认 180s）
  → 返回 session_id + tokens

POST /transfer/upload (offset=已收字节数)
  → 校验 offset == file.received
  → 流式追加到 .part，更新进度
  → 收满 → verifying

POST /transfer/complete
  → 可选 SHA-256 校验
  → sanitize rel_path + safe_join + unique_path
  → os.replace(.part → 接收目录)
  → 所有文件完成 → completed + 历史
```

## 发送流程

```text
expand_paths()
  → 创建 outbound Transfer（状态 waiting）
  → POST /transfer/request（挂起等待对方确认）
  → 逐文件：GET status → POST upload(offset) → POST complete(sha256)
  → 完成 / 取消 / 失败 → 更新 Transfer + 历史
```

每个文件最多重试 3 次；`409` 会读取服务端 `received` 并继续；网络错误会重新查询断点。取消会向接收方发 `/transfer/cancel`。

## GUI 结构

```text
MainWindow
├─ Sidebar：品牌、发送/传输/历史/设置、手机网页卡片、本机信息
├─ Topbar：页面标题、在线、HTTP/HTTPS 优先、刷新
├─ SendPage
│  ├─ Hero 卡片（HeroLogo 自绘星轨动画）
│  ├─ 设备卡片横向列表 + 手动连接 IP
│  ├─ DropZone（拖拽/点击）
│  ├─ 选择文件/文件夹/文本/剪贴板
│  ├─ 待发送列表
│  └─ 固定底部目标 + 发送按钮
├─ TransfersPage：TransferCard 列表 + 进度
├─ HistoryPage：QTableWidget
└─ SettingsPage：设备、连接、安全、外观/启动、关于
```

- `HeroLogo` 用 QPainter 每 32ms 重绘：星芒呼吸、两条轨道旋转、光晕脉动。
- `ReceiveDialog` 在 HTTP 线程等待时由主线程弹出；接受/拒绝后调用 `decide_pending`。
- `QSystemTrayIcon`：关闭窗口缩到托盘，菜单可显示/发送/退出；可写 HKCU Run 实现开机自启。

## 手机网页

- 由电脑托管；HTTP/HTTPS 同源页面均可加载。
- 6 位配对码 → token；SSE 每秒推送状态。
- 上传/下载、文本、offer、历史；浅/深色；首页星轨 SVG/CSS 动画。
- 设置里的 HTTPS 开关调用 `/web/settings`；「改用 HTTPS」跳到另一个端口并带 `?pair=` 自动重配。
- 局域网 HTTP 不是安全上下文，Service Worker/完整 PWA 安装会被浏览器跳过；这是协议之外的浏览器限制。

## 安全设计

- 路径清洗：`sanitize_name` / `sanitize_rel_path` / `safe_join`。
- 令牌：`secrets.token_urlsafe`；比较用 `hmac.compare_digest`。
- 配对限速：同 IP 每分钟 8 次。
- JSON 限制 16 MB，文本 1 MB，文件数 20000，单文件 512 GiB，总大小 2 TiB。
- 接收前检查磁盘剩余空间（预留 200 MB）。
- 接收端默认手动确认；手机网页因为先配对，视为可信。
- 不持久化网页 token；TLS 自签名只加密、不提供 CA 身份认证。

## 测试策略

`tests/test_e2e.py` 用真实 `AsterNode` + `PeerClient` 在 `127.0.0.1` 上起服务，覆盖：

1. 文件 + 文本接收、SHA 校验、历史
2. 文件夹相对路径、同名去重、零字节文件
3. 半包中断后的断点续传
4. 手动拒绝、错误 PIN、正确 PIN + 手动接受
5. 网页错误配对码、配对、手机上传、电脑 offer + Range 下载
6. UDP announce 发现
7. hello 手动连接、历史
8. 纯文本自动完成
9. HTTPS 网页访问、HTTPS 偏好切换、HTTPS 对等传输

另外：

- Puppeteer + Edge 390×844 手机视口：文本、6 MB 上传、offer 下载、主题、HTTPS 切换；
- Qt offscreen + 实际窗口：设备卡片、发送、接收确认、托盘、浅/深色；
- 1 GiB/4 GiB 测速：`tools/benchmark.py`。
