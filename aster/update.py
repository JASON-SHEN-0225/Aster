"""检查更新：官网 version.json 优先，GitHub Releases 回退。

这个模块只做网络读取与版本比较，不依赖 Qt / Windows，桌面端和网页服务端共用。
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from . import VERSION

UPDATE_URL = "https://asterdrop.cn/version.json"
GITHUB_API = "https://api.github.com/repos/JASON-SHEN-0225/Aster/releases/latest"
DOWNLOAD_PAGE = "https://asterdrop.cn/download.html"
CACHE_TTL = 600.0
TIMEOUT = 6.0

_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "data": None}


def parse_version(value: Any) -> tuple[int, ...]:
    """把 3.0.0 / v3.0.0 / 3.0.0-beta 转成可比较的数字元组。"""
    text = str(value or "").strip().lstrip("vV")
    match = re.match(r"^(\d+(?:\.\d+)*)", text)
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest: Any, current: Any = VERSION) -> bool:
    left = parse_version(latest)
    right = parse_version(current)
    if not left or not right:
        return False
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def _fetch_json(url: str) -> Optional[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Aster/{VERSION} (+https://asterdrop.cn)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            if response.status != 200:
                return None
            raw = response.read(2 * 1024 * 1024)
    except (OSError, urllib.error.URLError, ValueError):
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_website(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    version = str(data.get("version") or "").strip()
    if not version:
        return None
    desktop = data.get("desktop") if isinstance(data.get("desktop"), dict) else {}
    android = data.get("android") if isinstance(data.get("android"), dict) else {}
    return {
        "version": version,
        "released": str(data.get("released") or ""),
        "notes": str(data.get("notes") or ""),
        "page": str(data.get("download_page") or DOWNLOAD_PAGE),
        "desktop": {
            "version": str(desktop.get("version") or version),
            "url": str(desktop.get("url") or data.get("setup_url") or ""),
            "sha256": str(desktop.get("sha256") or ""),
            "size": int(desktop.get("size") or 0),
        },
        "android": {
            "version": str(android.get("version") or version),
            "versionCode": int(android.get("versionCode") or 0),
            "url": str(android.get("url") or ""),
            "sha256": str(android.get("sha256") or ""),
            "size": int(android.get("size") or 0),
        },
    }


def _normalize_github(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    version = str(data.get("tag_name") or data.get("name") or "").strip()
    if not version:
        return None
    version = version.lstrip("vV")
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    apk_url = ""
    setup_url = ""
    gui_url = ""
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").lower()
        url = str(asset.get("browser_download_url") or "")
        if not url:
            continue
        if name.endswith(".apk") and not apk_url:
            apk_url = url
        elif name.endswith(".exe"):
            if "setup" in name or "installer" in name:
                setup_url = setup_url or url
            else:
                gui_url = gui_url or url
    return {
        "version": version,
        "released": str(data.get("published_at") or "")[:10],
        "notes": str(data.get("body") or "")[:6000],
        "page": DOWNLOAD_PAGE,
        "desktop": {
            "version": version,
            "url": setup_url or gui_url,
            "sha256": "",
            "size": 0,
        },
        "android": {
            "version": version,
            "versionCode": 0,
            "url": apk_url,
            "sha256": "",
            "size": 0,
        },
    }


def fetch_manifest(force: bool = False) -> tuple[Optional[dict[str, Any]], str, str]:
    """返回 (manifest, source, error)。source 为 website / github / none。"""
    now = time.time()
    with _lock:
        cached = _cache.get("data")
        if not force and cached and now - float(_cache.get("at") or 0) < CACHE_TTL:
            return cached, str(_cache.get("source") or "none"), str(_cache.get("error") or "")

    website = _fetch_json(UPDATE_URL)
    if website:
        normalized = _normalize_website(website)
        if normalized:
            with _lock:
                _cache.update(at=now, data=normalized, source="website", error="")
            return normalized, "website", ""

    github = _fetch_json(GITHUB_API)
    if github:
        normalized = _normalize_github(github)
        if normalized:
            with _lock:
                _cache.update(at=now, data=normalized, source="github", error="")
            return normalized, "github", ""

    error = "无法连接更新服务器"
    with _lock:
        _cache.update(at=now, data=None, source="none", error=error)
    return None, "none", error


def check_update(current: str = VERSION, force: bool = False) -> dict[str, Any]:
    manifest, source, error = fetch_manifest(force=force)
    result: dict[str, Any] = {
        "ok": bool(manifest),
        "current": {"desktop": current, "android": current},
        "latest": manifest,
        "update_available": {
            "desktop": bool(manifest and is_newer(manifest["desktop"]["version"], current)),
            "android": bool(manifest and is_newer(manifest["android"]["version"], current)),
        },
        "source": source,
        "download_page": (manifest or {}).get("page") or DOWNLOAD_PAGE,
        "checked_at": time.time(),
        "error": error,
    }
    return result
