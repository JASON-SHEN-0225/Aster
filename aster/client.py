"""对等 HTTP 客户端：与另一台运行 Aster 的电脑通信。"""

from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from . import USER_AGENT, VERSION
from .tls import client_context
from .util import human_size, sanitize_name, sha256_file

MAX_RESPONSE = 8 * 1024 * 1024


class PeerError(Exception):
    def __init__(self, status: int, message: str, data: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.data = data or {}

    def __str__(self) -> str:
        return self.message


class CancelledError(Exception):
    pass


def _json_from_response(resp: http.client.HTTPResponse) -> dict[str, Any]:
    raw = resp.read(MAX_RESPONSE)
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise PeerError(resp.status, f"对端返回了无法解析的数据（HTTP {resp.status}）")
    if not isinstance(data, dict):
        raise PeerError(resp.status, f"对端返回格式异常（HTTP {resp.status}）")
    return data


class PeerClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float = 20.0,
        use_tls: bool = False,
    ):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.use_tls = bool(use_tls)
        self.scheme = "https" if self.use_tls else "http"

    # ------------------------------------------------------------------
    def _conn(self, timeout: Optional[float] = None) -> http.client.HTTPConnection:
        if self.use_tls:
            return http.client.HTTPSConnection(
                self.host,
                self.port,
                timeout=timeout or self.timeout,
                context=client_context(),
            )
        return http.client.HTTPConnection(
            self.host, self.port, timeout=timeout or self.timeout
        )

    def _json(
        self,
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        body = None
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Connection": "close",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        conn = self._conn(timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = _json_from_response(resp)
            if resp.status >= 400:
                message = str(data.get("error") or data.get("message") or f"HTTP {resp.status}")
                raise PeerError(resp.status, message, data)
            return data
        except PeerError:
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise PeerError(0, "连接超时，对方可能不在线或防火墙拦截") from exc
        except ssl.SSLError as exc:
            raise PeerError(0, f"TLS 握手失败（{exc}）") from exc
        except (ConnectionError, OSError, http.client.HTTPException) as exc:
            raise PeerError(0, f"无法连接 {self.host}:{self.port}（{exc}）") from exc
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def ping(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/ping", timeout=8)

    def info(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/info", timeout=10)

    def hello(self, device: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/api/v1/hello", {"device": device}, timeout=15)

    def request_transfer(
        self,
        device: dict[str, Any],
        files: list[dict[str, Any]],
        *,
        text: str = "",
        pin: str = "",
        timeout: float = 190.0,
    ) -> dict[str, Any]:
        payload = {
            "from": device,
            "files": files,
            "text": text,
            "pin": pin,
        }
        return self._json("POST", "/api/v1/transfer/request", payload, timeout=timeout)

    def get_status(self, session_id: str, file_id: str, token: str) -> dict[str, Any]:
        q = urlencode({"session_id": session_id, "file_id": file_id, "token": token})
        return self._json("GET", f"/api/v1/transfer/status?{q}", timeout=20)

    def upload_file(
        self,
        session_id: str,
        file_id: str,
        token: str,
        path: Path | str,
        *,
        offset: int = 0,
        progress: Optional[Callable[[int, int], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
        chunk_size: int = 256 * 1024,
        timeout: float = 90.0,
    ) -> tuple[dict[str, Any], Optional[str]]:
        path = Path(path)
        size = path.stat().st_size
        if offset < 0 or offset > size:
            raise PeerError(0, "断点偏移无效")
        remaining = size - offset
        q = urlencode(
            {
                "session_id": session_id,
                "file_id": file_id,
                "token": token,
                "offset": str(offset),
            }
        )
        conn = self._conn(timeout)
        import hashlib

        hasher = hashlib.sha256() if offset == 0 else None
        sent = 0
        try:
            conn.putrequest("POST", f"/api/v1/transfer/upload?{q}")
            conn.putheader("Host", f"{self.host}:{self.port}")
            conn.putheader("User-Agent", USER_AGENT)
            conn.putheader("Accept", "application/json")
            conn.putheader("Content-Type", "application/octet-stream")
            conn.putheader("Content-Length", str(remaining))
            conn.putheader("Connection", "close")
            conn.endheaders()
            with open(path, "rb") as fh:
                fh.seek(offset)
                while sent < remaining:
                    if cancel and cancel():
                        raise CancelledError()
                    chunk = fh.read(min(chunk_size, remaining - sent))
                    if not chunk:
                        raise PeerError(0, "读取文件时意外结束")
                    conn.send(chunk)
                    if hasher is not None:
                        hasher.update(chunk)
                    sent += len(chunk)
                    if progress:
                        progress(offset + sent, size)
            resp = conn.getresponse()
            data = _json_from_response(resp)
            if resp.status >= 400:
                message = str(data.get("error") or data.get("message") or f"HTTP {resp.status}")
                raise PeerError(resp.status, message, data)
            return data, (hasher.hexdigest() if hasher is not None else None)
        except CancelledError:
            raise
        except PeerError:
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise PeerError(0, "上传超时，可稍后重试续传") from exc
        except ssl.SSLError as exc:
            raise PeerError(0, f"TLS 连接中断（{exc}）") from exc
        except (ConnectionError, OSError, http.client.HTTPException) as exc:
            raise PeerError(0, f"上传中断（{exc}）") from exc
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def complete_file(
        self,
        session_id: str,
        file_id: str,
        token: str,
        sha256: Optional[str],
    ) -> dict[str, Any]:
        payload = {
            "session_id": session_id,
            "file_id": file_id,
            "token": token,
            "sha256": sha256 or "",
        }
        return self._json("POST", "/api/v1/transfer/complete", payload, timeout=900)

    def cancel(self, session_id: str, token: str, file_id: str = "") -> dict[str, Any]:
        payload = {"session_id": session_id, "token": token}
        if file_id:
            payload["file_id"] = file_id
        return self._json("POST", "/api/v1/transfer/cancel", payload, timeout=15)


# ---------------------------------------------------------------------------
# 发送侧文件收集
# ---------------------------------------------------------------------------

MAX_FILES = 20000


def _walk_folder(root: Path) -> tuple[list[Path], int]:
    files: list[Path] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # 跳过明显的回收站/临时目录，避免误发巨量文件
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "$RECYCLE.BIN")]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                if full.is_symlink() or not full.is_file():
                    continue
                files.append(full)
                total += full.stat().st_size
            except OSError:
                continue
            if len(files) > MAX_FILES:
                raise ValueError(f"文件数量超过 {MAX_FILES}，请分批发送")
    return files, total


def expand_paths(paths: list[str]) -> list[dict[str, Any]]:
    """展开文件/文件夹为传输清单。rel_path 保留顶层文件夹名。"""
    result: list[dict[str, Any]] = []
    seen_rel: set[str] = set()
    if not paths:
        raise ValueError("没有选择文件")
    for raw in paths:
        raw = str(raw).strip().strip('"').strip("'")
        if not raw:
            continue
        p = Path(os.path.expandvars(os.path.expanduser(raw)))
        try:
            p = p.resolve()
        except OSError:
            raise ValueError(f"路径无法解析：{raw}")
        if not p.exists():
            raise ValueError(f"路径不存在：{p}")
        if p.is_dir():
            root_name = p.name or "文件夹"
            files, _ = _walk_folder(p)
            if not files:
                raise ValueError(f"文件夹为空：{p}")
            for f in files:
                try:
                    rel = f.relative_to(p).as_posix()
                except ValueError:
                    rel = f.name
                rel = f"{root_name}/{rel}"
                if rel in seen_rel:
                    continue
                seen_rel.add(rel)
                result.append(
                    {
                        "id": uuid.uuid4().hex,
                        "name": f.name,
                        "rel_path": rel,
                        "size": f.stat().st_size,
                        "path": str(f),
                    }
                )
        elif p.is_file():
            name = p.name
            rel = name
            n = 1
            while rel in seen_rel:
                stem, suffix = p.stem, p.suffix
                rel = f"{stem} ({n}){suffix}"
                n += 1
            seen_rel.add(rel)
            result.append(
                {
                    "id": uuid.uuid4().hex,
                    "name": p.name,
                    "rel_path": rel,
                    "size": p.stat().st_size,
                    "path": str(p),
                }
            )
        else:
            raise ValueError(f"不支持的文件类型：{p}")
        if len(result) > MAX_FILES:
            raise ValueError(f"文件数量超过 {MAX_FILES}，请分批发送")
    if not result:
        raise ValueError("没有可发送的文件")
    return result


def public_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f["id"],
            "name": f.get("name") or Path(f["path"]).name,
            "rel_path": f.get("rel_path") or f.get("name"),
            "size": int(f.get("size") or 0),
        }
        for f in files
    ]


def total_size(files: list[dict[str, Any]]) -> int:
    return sum(int(f.get("size") or 0) for f in files)
