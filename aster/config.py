"""配置与设备身份。"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import socket
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import APP_NAME, DEFAULT_PORT, PROTOCOL_VERSION, VERSION
from .util import (
    atomic_write_json,
    default_download_dir,
    device_hostname,
    ensure_dir,
    get_lan_ip,
    platform_label,
    read_json,
)


def default_data_dir() -> Path:
    env = os.environ.get("ASTER_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
    return Path.home() / ".aster"


def new_pair_code() -> str:
    # 6 位，首位非零；足够防住随手扫网的请求，配合限速。
    return str(secrets.randbelow(900000) + 100000)


@dataclass
class Config:
    device_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    alias: str = field(default_factory=device_hostname)
    port: int = DEFAULT_PORT
    download_dir: str = ""
    auto_accept: bool = False
    pin: str = ""
    web_pairing: bool = True
    web_pair_code: str = field(default_factory=new_pair_code)
    request_timeout: int = 180
    theme: str = "light"
    prefer_https: bool = False
    https_port: int = 0
    created_at: float = field(default_factory=time.time)
    last_seen_version: str = VERSION

    def __post_init__(self) -> None:
        if not self.device_id:
            self.device_id = uuid.uuid4().hex
        if not self.alias:
            self.alias = device_hostname()
        if not self.web_pair_code:
            self.web_pair_code = new_pair_code()
        if not self.download_dir:
            self.download_dir = str(default_download_dir())
        self.port = int(self.port)
        if not (1024 <= self.port <= 65535):
            self.port = DEFAULT_PORT
        if not (30 <= int(self.request_timeout) <= 3600):
            self.request_timeout = 180
        if self.https_port:
            try:
                self.https_port = int(self.https_port)
            except (TypeError, ValueError):
                self.https_port = 0
            if not (1024 <= self.https_port <= 65535) or self.https_port == self.port:
                self.https_port = 0

    @property
    def tls_port(self) -> int:
        """HTTPS 端口：高级配置优先，否则默认 HTTP+1。"""
        if self.https_port and self.https_port != self.port:
            return self.https_port
        candidate = self.port + 1
        if candidate <= 65535:
            return candidate
        return max(1024, self.port - 1)

    # -- 身份 ---------------------------------------------------------
    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.device_id.encode("utf-8")).hexdigest()[:16]

    @property
    def web_url_code(self) -> str:
        return self.web_pair_code if self.web_pairing else ""

    def set_web_pair_code(self) -> str:
        self.web_pair_code = new_pair_code()
        return self.web_pair_code

    def device_info(self) -> dict[str, Any]:
        return {
            "id": self.device_id,
            "alias": self.alias,
            "device_type": "desktop",
            "version": VERSION,
            "protocol": PROTOCOL_VERSION,
            "platform": platform_label(),
            "fingerprint": self.fingerprint,
            "port": self.port,
            "https_port": self.tls_port,
            "prefer_https": bool(self.prefer_https),
            "web_url": self.web_url(include_code=False),
            "web_url_https": self.web_url(include_code=False, https=True),
            "auto_accept": bool(self.auto_accept),
            "requires_pin": bool(self.pin),
        }

    def web_url(self, include_code: bool = True, host: Optional[str] = None, https: bool = False) -> str:
        host = host or get_lan_ip()
        suffix = ""
        if include_code and self.web_pairing and self.web_pair_code:
            suffix = f"?pair={self.web_pair_code}"
        if https:
            return f"https://{host}:{self.tls_port}/{suffix}"
        return f"http://{host}:{self.port}/{suffix}"

    # -- 持久化 -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["version"] = VERSION
        return data

    def save(self, path: Path) -> None:
        atomic_write_json(path, self.to_dict())

    @classmethod
    def load(
        cls,
        data_dir: Optional[Path | str] = None,
        *,
        port: Optional[int] = None,
        alias: Optional[str] = None,
        download_dir: Optional[str | Path] = None,
        auto_accept: Optional[bool] = None,
        prefer_https: Optional[bool] = None,
    ) -> "Config":
        data_dir = Path(data_dir) if data_dir else default_data_dir()
        path = data_dir / "config.json"
        raw = read_json(path, {})
        if not isinstance(raw, dict):
            raw = {}
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        values = {k: v for k, v in raw.items() if k in known}
        cfg = cls(**values)
        if port is not None:
            cfg.port = int(port)
        if alias:
            cfg.alias = str(alias)[:48]
        if download_dir:
            cfg.download_dir = str(Path(download_dir).expanduser().resolve())
        if auto_accept is not None:
            cfg.auto_accept = bool(auto_accept)
        if prefer_https is not None:
            cfg.prefer_https = bool(prefer_https)
        ensure_dir(Path(cfg.download_dir))
        cfg.save(path)
        return cfg


class ConfigStore:
    """把配置和运行时目录绑在一起。"""

    def __init__(
        self,
        data_dir: Optional[Path | str] = None,
        *,
        port: Optional[int] = None,
        alias: Optional[str] = None,
        download_dir: Optional[str | Path] = None,
        auto_accept: Optional[bool] = None,
        prefer_https: Optional[bool] = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        ensure_dir(self.data_dir)
        self.path = self.data_dir / "config.json"
        self.config = Config.load(
            self.data_dir,
            port=port,
            alias=alias,
            download_dir=download_dir,
            auto_accept=auto_accept,
            prefer_https=prefer_https,
        )
        ensure_dir(Path(self.config.download_dir))

    def save(self) -> None:
        self.config.save(self.path)

    def rotate_pair_code(self) -> str:
        code = self.config.set_web_pair_code()
        self.save()
        return code

    @property
    def history_path(self) -> Path:
        return self.data_dir / "history.json"

    @property
    def tmp_dir(self) -> Path:
        return ensure_dir(self.data_dir / "tmp")

    @property
    def log_path(self) -> Path:
        return self.data_dir / "aster.log"

    def update(self, **kwargs: Any) -> Config:
        for key, value in kwargs.items():
            if key in self.config.__dataclass_fields__:  # type: ignore[attr-defined]
                setattr(self.config, key, value)
        self.config.__post_init__()
        ensure_dir(Path(self.config.download_dir))
        self.save()
        return self.config
