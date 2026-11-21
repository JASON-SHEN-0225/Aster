# Aster 协议 v1

Aster 的协议是自研的，不追求与 LocalSend 兼容。核心思想很简单：

> 同一局域网内，设备通过 UDP 多播互相发现；传输用 HTTP 会话；接收方发令牌，发送方按文件上传，支持断点续传和 SHA-256 校验。

- 传输层：HTTP 与 HTTPS 双端口并存
- HTTP 默认端口：`47820`（TCP 与 UDP 同号）
- HTTPS 默认端口：`47821`（HTTP+1，可配置）
- 数据：JSON 元数据 + `application/octet-stream` 文件体
- 字符编码：UTF-8
- 协议版本：`1`

## 1. 设备身份

每台电脑首次启动生成 `device_id`（UUID4 hex），保存在 `%APPDATA%\Aster\config.json`。设备信息：

```json
{
  "id": "32位hex",
  "alias": "客厅电脑",
  "device_type": "desktop",
  "version": "2.0.0",
  "protocol": 1,
  "platform": "Windows 11",
  "fingerprint": "sha256(device_id)[:16]",
  "port": 47820,
  "https_port": 47821,
  "prefer_https": false,
  "tls_fingerprint": "sha256(cert)[:32]",
  "ip": "192.168.1.23",
  "web_url": "http://192.168.1.23:47820/",
  "web_url_https": "https://192.168.1.23:47821/",
  "auto_accept": false,
  "requires_pin": false
}
```

手机网页不是独立的文件接收端，而是电脑的一个「网页会话」；它的设备 ID 形如 `web:<web_id>`，只在网页 API 内使用。

## 2. 发现

- UDP 绑定 `0.0.0.0:47820`
- 加入多播组 `239.255.42.99:47820`
- 同时向 `255.255.255.255:47820` 广播
- 启动时发 `query` + `announce`；之后每 4 秒 `announce`
- 13 秒未收到视为离线，1 小时后从内存清除
- 收到 `query` 时向来源单播 `announce`
- 设备信息同时携带 HTTP `port` 和 HTTPS `https_port`；对端据此选择协议

## 2.1 TLS / 自签名证书

- 启动时在 `%APPDATA%\Aster\certs\` 生成/复用自签名证书（RSA 2048，SAN 含 localhost、主机名、当前所有 IPv4，含 `127.0.0.1`）。
- 网卡 IP 变化时证书会重新生成，`tls_fingerprint` 随之变化。
- HTTPS 端口与 HTTP 同时监听；开关 `prefer_https` 只影响：
  - 二维码/默认网页地址；
  - 电脑↔电脑发送时优先使用 HTTPS（对端需有 `https_port`）。
- 客户端 HTTPS 使用加密连接但不校验证书链（自签名），仅用于局域网加密，不提供 CA 级身份认证。
- 手机浏览器首次访问 HTTPS 地址需要点「高级 → 继续访问」。

消息：

```json
{
  "app": "aster",
  "protocol": 1,
  "version": "2.0.0",
  "type": "announce",
  "device": { "...设备信息..." }
}
```

`type` 取值：`announce` / `query` / `bye`。设备收到自己的包会忽略。

手动连接不走发现：直接向 `ip:port` 发 `POST /api/v1/hello`。

## 3. 对等传输

### 3.0 选择 HTTP 还是 HTTPS

发送前：

1. 若本机 `prefer_https=true` 且本机 TLS 已启动，并且对端设备信息里 `https_port` 有效 → 走 HTTPS。
2. 否则走 HTTP。

HTTPS 连接使用自签名证书加密，但客户端不做 CA 校验。两种协议的业务端点、令牌、断点、SHA 校验完全一致。

### 3.1 发起

`POST /api/v1/transfer/request`

```json
{
  "from": { "...发送方设备信息..." },
  "files": [
    {
      "id": "32位hex",
      "name": "照片.jpg",
      "rel_path": "旅行/照片.jpg",
      "size": 123456
    }
  ],
  "text": "可选文本",
  "pin": "可选 PIN"
}
```

- `files` 可为空（纯文本）；`text` 也可为空（纯文件）；两者不能同时为空。
- 接收方若开启了 PIN，`pin` 必须匹配。
- 接收方默认弹出确认；确认前该 HTTP 请求保持挂起（超时 `request_timeout`，默认 180 秒）。
- 拒绝/超时返回 `403`。

接受响应：

```json
{
  "accepted": true,
  "session_id": "32位hex",
  "session_token": "随机串",
  "tokens": { "<file_id>": "<file_token>" },
  "peer_alias": "接收方名称",
  "resume": { "<file_id>": 0 },
  "auto_accepted": false
}
```

每个文件有独立 `file_token`；`session_token` 用于取消整个会话。

### 3.2 查询断点

`GET /api/v1/transfer/status?session_id=..&file_id=..&token=..`

```json
{
  "session_id": "...",
  "file_id": "...",
  "received": 524288,
  "size": 1048576,
  "status": "uploading",
  "session_status": "active"
}
```

### 3.3 上传

`POST /api/v1/transfer/upload?session_id=..&file_id=..&token=..&offset=524288`

- 请求体是文件从 `offset` 开始的原始字节。
- `Content-Length` 必须等于本次发送的字节数；不能分块传输。
- 服务端先写 `%APPDATA%\Aster\tmp\<session_id>\<file_id>.part`。
- `offset` 必须等于服务端当前已收字节数，否则返回 `409`，并带 `{"received": n}`。
- 收满 `size` 后文件状态变为 `verifying`，返回 `{"received": n, "complete": true, "needs_verify": true}`。

### 3.4 完成/校验

`POST /api/v1/transfer/complete`

```json
{
  "session_id": "...",
  "file_id": "...",
  "token": "...",
  "sha256": "可选，发送方对整个文件的 SHA-256"
}
```

- 若提供 `sha256`，接收方读取完整 `.part` 计算 SHA-256；不匹配则清空分片并返回 `422`。
- 校验通过后移动到接收目录：`download_dir/<sanitized rel_path>`；同名自动改成 `name (1).ext`。
- 所有文件完成后会话结束，写历史。
- 手机网页上传不传 `sha256`（浏览器不在大文件上做全量哈希），只做长度校验。

### 3.5 取消

`POST /api/v1/transfer/cancel`

```json
{"session_id": "...", "token": "<session_token 或任一 file_token>"}
```

接收方标记取消、删除分片（若上传线程仍在写则尽力而为），历史记为 `cancelled`。

## 4. 文本

文本作为 `request.files=[]` 的一部分发送。接收方一旦接受，就写入系统剪贴板并记一条历史；纯文本会话直接完成，无需上传。

## 5. 网页 API

网页由电脑托管在 `/`。所有 `/api/v1/web/*` 需要 Bearer token：

```
X-Aster-Web-Token: <token>
```

文件下载/SSE 因为浏览器限制，允许 `?token=<token>`。

### 5.1 配对

`POST /api/v1/web/pair`

```json
{"code": "123456", "name": "我的手机", "ua": "..."}
```

返回：

```json
{
  "token": "32字节随机串",
  "web_id": "32位hex",
  "web": {"id": "...", "name": "我的手机"},
  "device": { "...电脑信息..." },
  "state": { "...完整网页状态..." }
}
```

- 配对码在电脑面板显示，6 位数字；同一 IP 每分钟最多 8 次尝试。
- 关闭网页配对（`web_pairing=false`）时，`code` 可为空。
- token 只在配对响应里出现一次；服务端只保存 SHA-256。

### 5.2 状态与 SSE

`GET /api/v1/web/state`（header token）

`GET /api/v1/web/events?token=...`

SSE 每秒推送一帧完整状态：

```
data: {"device":{...},"transfers":[...],...}\n\n
```

没有 event 名，浏览器用 `EventSource.onmessage` 即可。状态包含：

- `device`、`peers`、`web_sessions`
- `transfers`：进行中/最近传输（方向、文件、进度、速度、ETA、状态）
- `offers`：电脑发给这个网页会话的接收请求
- `texts`：最近文本
- `history`：最近 24 条历史
- `settings`：自动接受、下载目录、HTTP/HTTPS 端口、`prefer_https`、TLS 指纹/错误等
- `http_url` / `https_url`：两种访问地址
- `pair_url`：按当前偏好的二维码地址
- `web`：当前网页会话
- `pairing.enabled`

### 5.3 手机上传到电脑

`POST /api/v1/web/request`

```json
{"files": [{"id":"32位hex","name":"a.jpg","rel_path":"相册/a.jpg","size":12345}]}
```

返回 `session_id`、`session_token`、`tokens`。之后复用对等上传接口：

`POST /api/v1/transfer/upload?...` + `POST /api/v1/transfer/complete`。

网页会话是已配对的，所以默认直接接受，不再在电脑上弹确认。

### 5.4 电脑发送到手机（Offer）

电脑端选择「手机网页」发送时创建 offer：

```json
{
  "id": "32位hex",
  "kind": "files",
  "status": "pending",
  "text": "可选",
  "files": [
    {
      "id": "...",
      "name": "a.jpg",
      "rel_path": "a.jpg",
      "size": 123,
      "sent": 0,
      "status": "pending",
      "url": "/api/v1/web/offers/<oid>/files/<fid>/download"
    }
  ],
  "created": 0,
  "updated": 0,
  "total_bytes": 123
}
```

- 手机调用 `POST /api/v1/web/offers/<oid>/respond`，body `{"accept": true|false}`。
- 接受后，手机用 `<url>?token=<web token>` 下载；支持 `Range`，断点/多线程下载可用。
- 下载完成（或 Range 覆盖到文件末尾）后 offer 标记 `completed`。
- 纯文本 offer 接受即完成。
- offer 24 小时未完成会过期。

### 5.5 文本/设置

- `POST /api/v1/web/text` `{"text":"..."}`：电脑写剪贴板 + 历史 + SSE `texts`。
- `POST /api/v1/web/settings` `{"auto_accept": true}`：修改全局接收策略。
- `POST /api/v1/web/settings` `{"prefer_https": true}`：切换默认协议；两个端口都已监听，不需要重启。返回快照中的 `settings.prefer_https`。

## 6. 状态码

| 状态 | 含义 |
|---|---|
| 200 | 成功 |
| 400 | 参数错误 / 上传中断 |
| 401 | 网页 token 失效 |
| 403 | PIN 错误 / 拒绝 / 配对码错误 |
| 404 | 会话/文件不存在 |
| 409 | 偏移不匹配 / 状态不允许 |
| 413 | 请求体过大 |
| 416 | Range 无效 |
| 422 | SHA-256 校验失败 |
| 429 | 配对尝试过于频繁 |
| 500 | 服务端错误 |
| 507 | 磁盘空间不足 |

## 7. 安全边界

- 局域网 HTTP 明文；HTTPS 用自签名证书加密，但客户端不校验证书链（首次需手动接受警告）。
- 不要把端口映射到公网。
- 对等传输的信任模型是「同网段 + 接收方确认 + 可选 PIN」。
- 网页会话用 6 位配对码换取高熵 token；token 只存哈希。
- 路径全部经过 `sanitize_rel_path` + `safe_join`，阻止 `..`、绝对路径、盘符逃逸。
- 文件名使用 `sanitize_name`，处理 Windows 保留名/非法字符/尾随空格。
- 服务端限制 JSON 体积、文件数、单文件/总大小、文本长度。
- 接收方确认超时默认 180 秒，超时视为拒绝。
