# 大文件传输测速（HTTP vs HTTPS）

## 结论先说

- **HTTPS 不会提升速度**。TLS 握手与加解密会带来额外 CPU/内存开销；本次实测 HTTPS 比 HTTP 慢约 **34–39%**。
- 追求速度就选 **HTTP 优先**；需要加密再打开 **HTTPS 优先**。
- 默认仍是 HTTP 优先；开关会记住上次选择。

## 测试条件

- 机器：Intel Core Ultra 9 275HX，Windows 11，D: 盘 SSD
- 方式：本机 loopback，两个 Aster 节点（发送端 / 接收端），均启用 SHA-256 完整性校验
- 文件：1 GiB / 4 GiB 顺序写入的二进制文件
- 协议：HTTP 48020 / HTTPS 48030（测试专用端口）
- 每次结果都核对接收文件 SHA-256 一致
- 时间包含：会话请求、上传、接收端 SHA-256 校验、落盘

> 这是 loopback 上限测试，不是 Wi-Fi 实测。真实 Wi-Fi（尤其 2.4 GHz、隔墙、AP 隔离）会明显更低；在真实网络里 TLS 的相对开销可能比这里小，因为瓶颈会变成无线链路。

## 测试命令

```powershell
python tools\benchmark.py --sizes 1,4 --modes http,https
```

结果 JSON：`build/benchmark/result.json`（测试目录会被忽略/清理）。

## 结果

| 模式 | 大小 | 耗时 | 吞吐 | SHA |
|---|---:|---:|---:|---|
| HTTP | 1 GiB | 1.31 s | **782.9 MiB/s** | ✓ |
| HTTP | 4 GiB | 5.75 s | **711.8 MiB/s** | ✓ |
| HTTPS | 1 GiB | 2.15 s | **475.6 MiB/s** | ✓ |
| HTTPS | 4 GiB | 8.74 s | **468.4 MiB/s** | ✓ |

- HTTP 1 GiB → 4 GiB 吞吐略降（782.9 → 711.8 MiB/s），磁盘/热缓存开始成为瓶颈。
- HTTPS 4 GiB 吞吐基本稳定在 468 MiB/s，说明瓶颈主要是 TLS + SHA/磁盘，而非网络。
- 两个模式均完整校验通过，没有出现截断或损坏。

## HTTPS 开关怎么用

1. 电脑 GUI：**设置 → 连接 → 优先使用 HTTPS**；手机网页：**设置 → HTTPS 加密优先**。
2. 打开后，二维码/默认网页地址会变成 `https://电脑IP:47821/`；电脑↔电脑传输也优先走 HTTPS。
3. 自签名证书首次会被浏览器标记为不安全：手机点 **高级 → 继续访问**。
4. 两个端口一直同时监听：HTTP `47820`、HTTPS `47821`；切换不需要重启。
5. 如果只是想最快速度：保持 HTTP 优先即可；需要防同网段嗅探时再开 HTTPS。

## 为什么 HTTPS 慢

- TLS 1.2+ 握手（首次连接）。
- 每个 HTTP 连接上的对称加解密（AES-GCM）。
- 本次 Aster 的文件上传本来就是 HTTP 流式发送；TLS 直接包在整条流上，因此 1 GiB/4 GiB 的持续传输都会多一层 CPU 运算。
- Python 的 `ssl` + `http.client` 单线程发送，TLS 开销在 Python 层更明显；如果改成多线程/异步，HTTPS 差距可能缩小，但不会变成“加速”。

## 后续可选优化

- 默认 HTTP，仅在对安全有要求时开 HTTPS（当前设计）。
- 使用 ECDSA 证书替代 RSA，降低握手开销；对大文件吞吐影响很小。
- 增加多连接并行上传（会提升吞吐，但也会增加接收端磁盘压力）。
- 评估 TLS 1.3 + session reuse；Python 版本较旧（3.10），升级 Python 可改善。
