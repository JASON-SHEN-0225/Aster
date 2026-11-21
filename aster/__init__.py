"""Aster · 星流 — 局域网文件互传。

一个自研协议的局域网传输工具：
  * 电脑端：PySide6 桌面 GUI，内置 HTTP/HTTPS 服务
  * 手机端：电脑托管的网页 + Android WebView APK
"""

APP_NAME = "Aster"
APP_CN = "星流"
TAGLINE = "局域网文件流转，快而克制"
VERSION = "2.0.0"
PROTOCOL_VERSION = 1
DEFAULT_PORT = 47820
MULTICAST_GROUP = "239.255.42.99"
USER_AGENT = f"Aster/{VERSION}"

__all__ = [
    "APP_NAME",
    "APP_CN",
    "TAGLINE",
    "VERSION",
    "PROTOCOL_VERSION",
    "DEFAULT_PORT",
    "MULTICAST_GROUP",
    "USER_AGENT",
]
