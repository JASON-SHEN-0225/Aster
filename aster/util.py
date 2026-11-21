"""通用工具：路径、格式化、网络、剪贴板、哈希。"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

IS_WINDOWS = os.name == "nt"

# ---------------------------------------------------------------------------
# 基础格式化
# ---------------------------------------------------------------------------


def human_size(num: float | int | None) -> str:
    """把字节数变成人类友好的字符串。"""
    if num is None:
        return "-"
    n = float(num)
    if n < 0:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    while n >= 1024 and idx < len(units) - 1:
        n /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(n)} {units[idx]}"
    if n >= 100:
        return f"{n:.0f} {units[idx]}"
    if n >= 10:
        return f"{n:.1f} {units[idx]}"
    return f"{n:.2f} {units[idx]}"


def human_speed(bps: float | None) -> str:
    if not bps or bps <= 0:
        return "-"
    return f"{human_size(bps)}/s"


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "-"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}分{sec:02d}秒"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}时{minutes:02d}分"


def format_time(ts: float | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def short_time(ts: float | None) -> str:
    if not ts:
        return "-"
    now = time.time()
    if now - ts < 60:
        return "刚刚"
    if now - ts < 3600:
        return f"{int((now - ts) / 60)} 分钟前"
    if now - ts < 86400:
        return f"{int((now - ts) / 3600)} 小时前"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def truncate(text: str, limit: int = 60) -> str:
    text = str(text).replace("\n", " ").replace("\r", " ")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 路径安全
# ---------------------------------------------------------------------------

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_name(name: str, fallback: str = "未命名文件") -> str:
    """清洗单个文件/目录名，去掉 Windows 非法字符。"""
    if not name:
        return fallback
    name = unicodedata.normalize("NFC", str(name)).strip()
    name = _BAD_CHARS.sub("_", name)
    name = name.rstrip(" .")
    if not name:
        return fallback
    stem = name.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED:
        name = "_" + name
    if len(name) > 180:
        suffix = Path(name).suffix[:16]
        name = name[: 180 - len(suffix)] + suffix
    return name


def sanitize_rel_path(rel: str | None, fallback_name: str = "未命名文件") -> str:
    """把对端传来的相对路径变成安全路径；拒绝 .. / 绝对路径 / 盘符。"""
    if not rel:
        return sanitize_name(fallback_name)
    rel = str(rel).replace("\\", "/").strip()
    rel = rel.lstrip("/")
    if re.match(r"^[A-Za-z]:", rel):
        rel = rel.split(":", 1)[1].lstrip("/")
    parts: list[str] = []
    for raw in rel.split("/"):
        if raw in ("", ".", ".."):
            continue
        part = sanitize_name(raw)
        if part and part not in (".", ".."):
            parts.append(part)
    if not parts:
        return sanitize_name(fallback_name)
    return "/".join(parts[-24:])


def safe_join(base: Path | str, rel: str) -> Path:
    """在 base 下安全拼接相对路径，越界时抛 ValueError。"""
    base = Path(base).resolve()
    target = (base / Path(str(rel).replace("\\", "/"))).resolve()
    try:
        common = os.path.commonpath([str(base), str(target)])
    except ValueError as exc:  # 不同盘符
        raise ValueError("路径越界") from exc
    if os.path.normcase(common) != os.path.normcase(str(base)):
        raise ValueError("路径越界")
    return target


def unique_path(path: Path) -> Path:
    """若已存在，追加 (1)(2)…"""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    for i in range(1, 10000):
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("无法生成唯一文件名")


def ensure_dir(path: Path | str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def atomic_write_json(path: Path | str, obj: Any) -> None:
    data = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")
    atomic_write_bytes(path, data)


def read_json(path: Path | str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def default_download_dir() -> Path:
    """优先读 Windows 已知文件夹「下载」，否则用 ~/Downloads。"""
    if IS_WINDOWS:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            )
            value, _ = winreg.QueryValueEx(
                key, "{374DE290-123F-4565-9164-39C4925E467B}"
            )
            path = Path(os.path.expandvars(value))
            if path:
                return path / "Aster"
        except Exception:
            pass
    return Path.home() / "Downloads" / "Aster"


# ---------------------------------------------------------------------------
# 网络
# ---------------------------------------------------------------------------


def get_lan_ip() -> str:
    """获取默认路由对应的局域网 IPv4，不真正发包。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def get_interface_ips() -> list[str]:
    """尽量列出本机可用于多播的 IPv4。"""
    ips: list[str] = []
    for candidate in (get_lan_ip(),):
        if candidate and not candidate.startswith("127."):
            ips.append(candidate)
    try:
        host = socket.gethostname()
        for item in socket.gethostbyname_ex(host)[2]:
            if item and not item.startswith("127.") and item not in ips:
                if not item.startswith("169.254."):
                    ips.append(item)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def platform_label() -> str:
    if IS_WINDOWS:
        try:
            release = platform.release()
            if release.startswith("10"):
                # Windows 11 的 release 仍是 10；用 build 号区分
                build = int(platform.version().split(".")[-1])
                if build >= 22000:
                    return "Windows 11"
                return "Windows 10"
            if release == "7":
                return "Windows 7"
            return f"Windows {release}"
        except Exception:
            return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    return platform.system() or "Linux"


def device_hostname() -> str:
    try:
        name = socket.gethostname().strip()
    except OSError:
        name = ""
    if not name:
        return "我的电脑"
    name = re.sub(r"\.local$", "", name, flags=re.I)
    return name[:48]


def split_host_port(target: str, default_port: int) -> tuple[str, int]:
    target = target.strip()
    if target.startswith("["):  # [ipv6]:port
        end = target.find("]")
        host = target[1:end]
        rest = target[end + 1 :]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, default_port
    if target.count(":") == 1:
        host, maybe_port = target.rsplit(":", 1)
        if maybe_port.isdigit():
            return host, int(maybe_port)
    return target, default_port


def url_encode_path(rel: str) -> str:
    from urllib.parse import quote

    return quote(rel.replace("\\", "/"), safe="/")


# ---------------------------------------------------------------------------
# 校验与剪贴板
# ---------------------------------------------------------------------------


def sha256_file(
    path: Path | str,
    chunk_size: int = 1024 * 1024,
    callback: Optional[Callable[[int], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> str:
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as fh:
        while True:
            if cancel and cancel():
                raise InterruptedError("已取消")
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
            if callback:
                callback(total)
    return h.hexdigest()


# Windows 剪贴板：用 ctypes 直接操作，避免 clip.exe 的编码问题。
if IS_WINDOWS:
    _CF_UNICODETEXT = 13
    _GMEM_MOVEABLE = 0x0002
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = ctypes.c_void_p
    _kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalUnlock.restype = ctypes.c_int
    _kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalFree.restype = ctypes.c_void_p
    _user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    _user32.OpenClipboard.restype = ctypes.c_int
    _user32.CloseClipboard.restype = ctypes.c_int
    _user32.EmptyClipboard.restype = ctypes.c_int
    _user32.GetClipboardData.argtypes = [ctypes.c_uint]
    _user32.GetClipboardData.restype = ctypes.c_void_p
    _user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    _user32.SetClipboardData.restype = ctypes.c_void_p

    def get_clipboard_text() -> str:
        for _ in range(3):
            if not _user32.OpenClipboard(None):
                time.sleep(0.05)
                continue
            try:
                handle = _user32.GetClipboardData(_CF_UNICODETEXT)
                if not handle:
                    return ""
                ptr = _kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    _kernel32.GlobalUnlock(handle)
            finally:
                _user32.CloseClipboard()
        return ""

    def set_clipboard_text(text: str) -> bool:
        data = str(text).encode("utf-16-le") + b"\x00\x00"
        handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            _kernel32.GlobalFree(handle)
            return False
        try:
            ctypes.memmove(ptr, data, len(data))
        finally:
            _kernel32.GlobalUnlock(handle)
        for _ in range(3):
            if not _user32.OpenClipboard(None):
                time.sleep(0.05)
                continue
            try:
                _user32.EmptyClipboard()
                if _user32.SetClipboardData(_CF_UNICODETEXT, handle):
                    return True
            finally:
                _user32.CloseClipboard()
        _kernel32.GlobalFree(handle)
        return False

else:  # pragma: no cover - 非 Windows 兜底

    def get_clipboard_text() -> str:
        try:
            if sys.platform == "darwin":
                return subprocess.check_output(["pbpaste"]).decode("utf-8", "replace")
            return subprocess.check_output(
                ["xclip", "-selection", "clipboard", "-o"]
            ).decode("utf-8", "replace")
        except Exception:
            return ""

    def set_clipboard_text(text: str) -> bool:
        try:
            if sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=str(text).encode("utf-8"), check=True)
            else:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=str(text).encode("utf-8"),
                    check=True,
                )
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# 资源路径与杂项
# ---------------------------------------------------------------------------


def resource_path(*parts: str) -> Path:
    """兼容源码运行与 PyInstaller --onefile。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


def webui_path() -> Path:
    if getattr(sys, "frozen", False):
        return resource_path("aster", "webui")
    return Path(__file__).resolve().parent / "webui"


def project_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.joinpath(*parts)
    return Path(__file__).resolve().parent.parent.joinpath(*parts)


def set_console_title(title: str) -> None:
    if IS_WINDOWS:
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(str(title))
        except Exception:
            pass


def open_in_browser(url: str) -> bool:
    try:
        if IS_WINDOWS:
            os.startfile(url)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        return True
    except Exception:
        return False


def is_admin() -> bool:
    if not IS_WINDOWS:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
