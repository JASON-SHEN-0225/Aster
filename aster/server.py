"""Aster 节点：HTTP 服务端、接收会话、网页 API、发送编排。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import APP_NAME, PROTOCOL_VERSION, VERSION
from .client import (
    CancelledError,
    PeerClient,
    PeerError,
    expand_paths,
    public_files,
    total_size,
)
from . import update as update_mod
from .config import ConfigStore
from .discovery import DiscoveryService
from .history import HistoryStore
from .tls import TLSMaterial, ensure_cert, server_context
from .util import (
    atomic_write_json,
    ensure_dir,
    format_duration,
    get_lan_ip,
    human_size,
    human_speed,
    safe_join,
    sanitize_name,
    sanitize_rel_path,
    set_clipboard_text,
    sha256_file,
    unique_path,
    webui_path,
)

LOG = logging.getLogger("aster.node")

MAX_JSON_BODY = 16 * 1024 * 1024
MAX_TEXT = 1024 * 1024
MAX_FILES = 20000
MAX_FILE_SIZE = 512 * 1024 * 1024 * 1024  # 512 GiB
MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024 * 1024  # 2 TiB

ACTIVE_TRANSFER_STATUSES = (
    "waiting",
    "pending",
    "active",
    "uploading",
    "verifying",
)


class ApiError(Exception):
    def __init__(self, status: int, message: str, data: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.data = data or {}


# ---------------------------------------------------------------------------
# 内部数据结构
# ---------------------------------------------------------------------------


@dataclass
class IncomingFile:
    id: str
    name: str
    rel_path: str
    size: int
    token: str
    part_path: Path
    received: int = 0
    status: str = "pending"
    expected_sha256: str = ""
    actual_sha256: str = ""
    final_path: str = ""
    error: str = ""
    updated: float = 0.0


@dataclass
class IncomingSession:
    id: str
    token: str
    peer: dict[str, Any]
    via: str
    web_id: str
    files: dict[str, IncomingFile]
    text: str
    status: str
    created: float
    updated: float
    transfer_id: str
    entry_id: str
    cancel_requested: bool = False
    active_handlers: set[Any] = field(default_factory=set)


@dataclass
class PendingRequest:
    id: str
    session: IncomingSession
    created: float
    event: threading.Event = field(default_factory=threading.Event)
    decision: Optional[bool] = None
    prompted: bool = False


@dataclass
class WebSession:
    id: str
    name: str
    ua: str
    token_hash: str
    created: float
    last_seen: float
    ip: str
    client: str = "web"
    connected: bool = False


@dataclass
class WebOffer:
    id: str
    web_id: str
    files: list[dict[str, Any]]
    text: str
    status: str
    created: float
    updated: float
    entry_id: str
    transfer_id: str


# ---------------------------------------------------------------------------
# 节点
# ---------------------------------------------------------------------------


class AsterNode:
    def __init__(
        self,
        store: ConfigStore,
        *,
        port: Optional[int] = None,
        enable_discovery: bool = True,
        console_decisions: bool = False,
    ):
        self.store = store
        self.config = store.config
        self.port = int(port if port is not None else self.config.port)
        self.https_port = int(self.config.https_port or 0)
        if not (1024 <= self.https_port <= 65535) or self.https_port == self.port:
            self.https_port = self.port + 1 if self.port < 65535 else self.port - 1
        self.lan_ip = get_lan_ip()
        self.enable_discovery = enable_discovery
        self.console_decisions = console_decisions
        self.tls_material: Optional[TLSMaterial] = None
        self.httpsd: Optional[ThreadingHTTPServer] = None
        self._https_thread: Optional[threading.Thread] = None
        self.tls_error = ""

        self.lock = threading.RLock()
        self.transfers: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, IncomingSession] = {}
        self.pending: dict[str, PendingRequest] = {}
        self.web_sessions: dict[str, WebSession] = {}
        self.offers: dict[str, WebOffer] = {}
        self.manual_peers: dict[str, dict[str, Any]] = {}
        self.texts: deque[dict[str, Any]] = deque(maxlen=50)
        self._speed_samples: dict[str, deque[tuple[float, int]]] = {}
        self._pair_attempts: dict[str, list[float]] = {}
        self._offer_cancel: dict[str, threading.Event] = {}
        self._offer_sockets: dict[str, set[Any]] = {}
        self._cancel_events: dict[str, threading.Event] = {}

        self.history = HistoryStore(store.history_path)
        self.discovery: Optional[DiscoveryService] = None
        self.httpd: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._console_thread: Optional[threading.Thread] = None
        self._prune_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.running = False
        self.started_at = 0.0

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.running:
            return
        if not (1 <= self.port <= 65535):
            raise RuntimeError("端口范围应为 1-65535")
        try:
            self.httpd = AsterHTTPServer(("0.0.0.0", self.port), AsterHandler)
        except OSError as exc:
            raise RuntimeError(
                f"端口 {self.port} 无法监听（可能被占用）。\n"
                f"可以换端口：aster --port 47821，或关闭占用该端口的程序。\n"
                f"原始错误：{exc}"
            ) from exc
        self.httpd.node = self  # type: ignore[attr-defined]
        self.port = int(self.httpd.server_port)
        self.lan_ip = get_lan_ip()
        self._server_thread = threading.Thread(
            target=self.httpd.serve_forever, name="aster-http", daemon=True
        )
        self._server_thread.start()
        self._start_https()
        self.running = True
        self.started_at = time.time()
        if self.enable_discovery:
            self.discovery = DiscoveryService(self.device_info, self.port)
            if not self.discovery.start():
                LOG.warning("多播发现不可用，仍可通过输入 IP 连接")
        if self.console_decisions:
            self._console_thread = threading.Thread(
                target=self._console_decision_loop, name="aster-console", daemon=True
            )
            self._console_thread.start()
        self._prune_thread = threading.Thread(
            target=self._prune_loop, name="aster-prune", daemon=True
        )
        self._prune_thread.start()
        self._prune()
        LOG.info("Aster 已启动：http://%s:%s/", self.lan_ip, self.port)
        if self.tls_material:
            LOG.info("Aster HTTPS：https://%s:%s/", self.lan_ip, self.https_port)

    def _start_https(self) -> None:
        """启动 HTTPS 监听；失败时保留 HTTP，并记录原因。"""
        if self.https_port == self.port or not (1024 <= self.https_port <= 65535):
            self.tls_error = "HTTPS 端口无效"
            return
        try:
            material = ensure_cert(self.store.data_dir, [self.lan_ip, "127.0.0.1"])
            httpd = AsterHTTPServer(("0.0.0.0", self.https_port), AsterHandler)
            httpd.node = self  # type: ignore[attr-defined]
            httpd.socket = server_context(material).wrap_socket(
                httpd.socket, server_side=True
            )
        except Exception as exc:
            self.tls_error = str(exc)
            LOG.warning("HTTPS 启动失败，继续使用 HTTP：%s", exc)
            return
        self.tls_material = material
        self.httpsd = httpd
        self.https_port = int(httpd.server_port)
        self._https_thread = threading.Thread(
            target=httpd.serve_forever, name="aster-https", daemon=True
        )
        self._https_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        if self.discovery:
            try:
                self.discovery.stop()
            except Exception:
                pass
        for server in (self.httpd, self.httpsd):
            if server:
                try:
                    server.shutdown()
                except Exception:
                    pass
                try:
                    server.server_close()
                except Exception:
                    pass
        for th in (self._server_thread, self._https_thread, self._console_thread, self._prune_thread):
            if th and th.is_alive():
                th.join(timeout=2.0)

    # ------------------------------------------------------------------
    # 设备/网络状态
    # ------------------------------------------------------------------
    def device_info(self) -> dict[str, Any]:
        info = self.config.device_info()
        info.update(
            {
                "port": self.port,
                "https_port": self.https_port if self.tls_material else 0,
                "prefer_https": bool(self.config.prefer_https and self.tls_material),
                "tls_fingerprint": (
                    self.tls_material.fingerprint[:32] if self.tls_material else ""
                ),
                "ip": self.lan_ip,
                "web_url": self.web_url(https=False),
                "web_url_https": self.web_url(https=True),
                "auto_accept": bool(self.config.auto_accept),
                "requires_pin": bool(self.config.pin),
            }
        )
        return info

    def web_url(self, https: bool = False) -> str:
        if https and self.tls_material:
            return f"https://{self.lan_ip}:{self.https_port}/"
        return f"http://{self.lan_ip}:{self.port}/"

    def pair_url(self, https: Optional[bool] = None) -> str:
        use_https = bool(self.config.prefer_https and self.tls_material) if https is None else bool(https and self.tls_material)
        url = self.web_url(https=use_https)
        if self.config.web_pairing:
            url += f"?pair={self.config.web_pair_code}"
        return url

    def set_prefer_https(self, enabled: bool) -> None:
        if enabled and not self.tls_material:
            raise ValueError(f"HTTPS 不可用：{self.tls_error or '证书未启动'}")
        self.config.prefer_https = bool(enabled)
        self.store.save()
        if self.discovery:
            self.discovery.send_announce()

    def set_alias(self, name: str) -> None:
        name = str(name).strip()[:48]
        if not name:
            raise ValueError("设备名称不能为空")
        self.config.alias = name
        self.store.save()
        if self.discovery:
            self.discovery.send_announce()

    def set_auto_accept(self, enabled: bool) -> None:
        self.config.auto_accept = bool(enabled)
        self.store.save()

    def rotate_pair_code(self) -> str:
        code = self.store.rotate_pair_code()
        return code

    def refresh_discovery(self) -> None:
        """主动重发发现查询，用于 GUI 的“搜索附近设备”。"""
        if not self.discovery:
            return
        try:
            self.discovery.send_query()
            self.discovery.send_announce()
        except OSError:
            LOG.debug("主动搜索设备失败", exc_info=True)

    def list_peers(self, include_offline: bool = True) -> list[dict[str, Any]]:
        peers: dict[str, dict[str, Any]] = {}
        if self.discovery:
            for p in self.discovery.list_peers(include_offline=include_offline):
                peers[str(p.get("id"))] = p
        now = time.time()
        for pid, p in self.manual_peers.items():
            item = dict(p)
            item["online"] = (now - float(item.get("last_seen") or 0)) <= 30
            if item["online"] or include_offline:
                peers.setdefault(pid, item)
        result = list(peers.values())
        result.sort(key=lambda p: (not bool(p.get("online")), str(p.get("alias", "")).lower()))
        return result

    def get_peer(self, peer_id: str) -> Optional[dict[str, Any]]:
        for p in self.list_peers():
            if str(p.get("id")) == str(peer_id):
                return p
        return None

    def remember_peer(self, device: dict[str, Any], ip: str, port: Optional[int] = None) -> dict[str, Any]:
        if not isinstance(device, dict) or not device.get("id"):
            raise ApiError(400, "设备信息不完整")
        peer = dict(device)
        peer["ip"] = ip
        try:
            peer["port"] = int(port or device.get("port") or self.port)
        except (TypeError, ValueError):
            peer["port"] = self.port
        peer["last_seen"] = time.time()
        peer["online"] = True
        peer.setdefault("device_type", "desktop")
        self.manual_peers[str(peer["id"])] = peer
        if self.discovery:
            with self.discovery._lock:  # 与发现服务共享同一份在线表
                self.discovery.peers[str(peer["id"])] = dict(peer)
        return peer

    def list_web_sessions(self) -> list[dict[str, Any]]:
        now = time.time()
        with self.lock:
            result = [
                {
                    "id": ws.id,
                    "name": ws.name,
                    "ua": ws.ua,
                    "ip": ws.ip,
                    "online": (now - ws.last_seen) <= 20,
                    "connected": ws.connected,
                    "last_seen": ws.last_seen,
                    "created": ws.created,
                    "device_type": "web",
                    "client": ws.client,
                }
                for ws in self.web_sessions.values()
            ]
        result.sort(key=lambda x: (not x["online"], x["name"].lower()))
        return result

    # ------------------------------------------------------------------
    # 快照
    # ------------------------------------------------------------------
    def _public_transfer(self, t: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in t.items() if not k.startswith("_")}
        out["files"] = [dict(f) for f in t.get("files", [])]
        out["peer"] = dict(t.get("peer") or {})
        return out

    def _public_offer(self, offer: WebOffer, include_urls: bool = False) -> dict[str, Any]:
        files = []
        transfer = self.transfers.get(offer.transfer_id) or {}
        for f in offer.files:
            item = {
                "id": f["id"],
                "name": f["name"],
                "rel_path": f["rel_path"],
                "size": f["size"],
                "sent": f.get("sent", 0),
                "status": f.get("status", "pending"),
            }
            if include_urls:
                item["url"] = f"/api/v1/web/offers/{offer.id}/files/{f['id']}/download"
            files.append(item)
        return {
            "id": offer.id,
            "kind": "files" if files else "text",
            "status": offer.status,
            "text": offer.text,
            "files": files,
            "created": offer.created,
            "updated": offer.updated,
            "total_bytes": sum(int(f["size"]) for f in files),
            "transfer_status": transfer.get("status", ""),
            "done_bytes": sum(int(f.get("sent") or 0) for f in files),
            "speed": transfer.get("speed", 0.0),
            "avg_speed": transfer.get("avg_speed", 0.0),
            "eta": transfer.get("eta"),
        }

    def snapshot(self, *, include_all_offers: bool = True) -> dict[str, Any]:
        with self.lock:
            transfers = [self._public_transfer(t) for t in self.transfers.values()]
            transfers.sort(
                key=lambda t: (
                    0
                    if t.get("status") in ("waiting", "active", "verifying", "pending")
                    else 1,
                    -float(t.get("started_at") or 0),
                )
            )
            transfers = transfers[:24]
            pending = [
                {
                    "id": p.id,
                    "session_id": p.session.id,
                    "peer": self._peer_public(p.session.peer),
                    "files": [
                        {"name": f.name, "rel_path": f.rel_path, "size": f.size}
                        for f in p.session.files.values()
                    ],
                    "text": p.session.text,
                    "created": p.created,
                    "expires_in": max(
                        0,
                        int(self.config.request_timeout - (time.time() - p.created)),
                    ),
                }
                for p in self.pending.values()
                if p.decision is None
            ]
            offers = [self._public_offer(o) for o in self.offers.values() if o.status != "expired"]
            offers = offers[-20:]
            texts = list(self.texts)[-20:][::-1]
        return {
            "app": APP_NAME,
            "version": VERSION,
            "protocol": PROTOCOL_VERSION,
            "server_time": time.time(),
            "device": self.device_info(),
            "peers": self.list_peers(),
            "web_sessions": self.list_web_sessions(),
            "transfers": transfers,
            "pending": pending,
            "offers": offers if include_all_offers else [],
            "texts": texts,
            "history": self.history.list(24),
            "settings": {
                "auto_accept": bool(self.config.auto_accept),
                "web_pairing": bool(self.config.web_pairing),
                "download_dir": self.config.download_dir,
                "port": self.port,
                "https_port": self.https_port,
                "prefer_https": bool(self.config.prefer_https and self.tls_material),
                "tls_enabled": bool(self.tls_material),
                "tls_error": self.tls_error,
                "tls_fingerprint": (
                    self.tls_material.fingerprint[:32] if self.tls_material else ""
                ),
                "request_timeout": self.config.request_timeout,
                "version": VERSION,
                "update_url": update_mod.UPDATE_URL,
                "download_page": update_mod.DOWNLOAD_PAGE,
            },
            "pair_url": self.pair_url(),
            "web_url": self.web_url(https=False),
            "web_url_https": self.web_url(https=True),
        }

    def web_state(self, ws: WebSession) -> dict[str, Any]:
        state = self.snapshot(include_all_offers=False)
        with self.lock:
            offers = [
                self._public_offer(o, include_urls=True)
                for o in self.offers.values()
                if o.web_id == ws.id and o.status != "expired"
            ]
        offers = offers[-20:]
        state["web"] = {
            "id": ws.id,
            "name": ws.name,
            "client": ws.client,
            "paired": True,
            "online": True,
        }
        state["offers"] = offers
        state["pairing"] = {"enabled": bool(self.config.web_pairing)}
        state["http_url"] = self.web_url(https=False)
        state["https_url"] = self.web_url(https=True)
        return state

    @staticmethod
    def _peer_public(peer: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "id",
            "alias",
            "device_type",
            "client",
            "version",
            "platform",
            "fingerprint",
            "ip",
            "port",
            "https_port",
            "prefer_https",
            "tls_fingerprint",
            "web_url",
            "web_url_https",
            "online",
            "last_seen",
        )
        return {k: peer.get(k) for k in keys if peer.get(k) is not None}

    # ------------------------------------------------------------------
    # 传输状态
    # ------------------------------------------------------------------
    def _new_transfer(
        self,
        *,
        direction: str,
        via: str,
        peer: dict[str, Any],
        files: list[dict[str, Any]],
        text: str,
        status: str,
        transfer_id: Optional[str] = None,
    ) -> dict[str, Any]:
        tid = transfer_id or uuid.uuid4().hex
        now = time.time()
        public_files = []
        for f in files:
            public_files.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "rel_path": f.get("rel_path") or f["name"],
                    "size": int(f.get("size") or 0),
                    "done": 0,
                    "status": "pending",
                }
            )
        transfer = {
            "id": tid,
            "direction": direction,
            "via": via,
            "kind": "files" if public_files else "text",
            "peer": self._peer_public(peer),
            "files": public_files,
            "text": text,
            "status": status,
            "total_bytes": sum(int(f["size"]) for f in public_files),
            "done_bytes": 0,
            "speed": 0.0,
            "avg_speed": 0.0,
            "eta": None,
            "current_file": "",
            "started_at": now,
            "finished_at": None,
            "error": "",
            "entry_id": "",
        }
        with self.lock:
            self.transfers[tid] = transfer
            self._speed_samples[tid] = deque(maxlen=12)
            history_kind = (
                "text_receive"
                if direction == "in" and not public_files
                else "text_send"
                if direction == "out" and not public_files
                else "receive"
                if direction == "in"
                else "send"
            )
            entry = HistoryStore.new_entry(
                kind=history_kind,
                direction=direction,
                peer=self._peer_public(peer),
                files=[{"name": f["name"], "rel_path": f["rel_path"], "size": f["size"]} for f in public_files],
                text=text,
                via=via,
                status="pending",
            )
            self.history.add(entry)
            transfer["entry_id"] = entry["id"]
        return transfer

    def _progress(self, transfer_id: str, done: int, current_file: str = "") -> None:
        now = time.time()
        with self.lock:
            t = self.transfers.get(transfer_id)
            if not t:
                return
            total = int(t.get("total_bytes") or 0)
            done = max(0, min(int(done), total if total else int(done)))
            t["done_bytes"] = done
            if current_file:
                t["current_file"] = current_file
            samples = self._speed_samples.setdefault(transfer_id, deque(maxlen=12))
            samples.append((now, done))
            while samples and now - samples[0][0] > 4.0:
                samples.popleft()
            speed = 0.0
            if len(samples) >= 2:
                dt = samples[-1][0] - samples[0][0]
                if dt > 0.05:
                    speed = max(0.0, (samples[-1][1] - samples[0][1]) / dt)
            started = float(t.get("started_at") or now)
            elapsed = max(0.001, now - started)
            avg_speed = (done / elapsed) if done > 0 else 0.0
            if speed <= 0 and done > 0:
                # 短文件可能只有一两个采样点；用整体平均速度兜底，避免 0 B/s。
                speed = avg_speed
            t["speed"] = speed
            t["avg_speed"] = avg_speed
            remaining = max(0, total - done)
            t["eta"] = (remaining / speed) if speed > 0 and remaining > 0 else (0 if remaining == 0 else None)

    def _file_public_by_id(self, transfer_id: str, file_id: str) -> Optional[dict[str, Any]]:
        t = self.transfers.get(transfer_id)
        if not t:
            return None
        for f in t.get("files", []):
            if f.get("id") == file_id:
                return f
        return None

    def _set_file_status(
        self, transfer_id: str, file_id: str, status: str, done: Optional[int] = None
    ) -> None:
        with self.lock:
            f = self._file_public_by_id(transfer_id, file_id)
            if not f:
                return
            f["status"] = status
            if done is not None:
                f["done"] = int(done)
            total = sum(int(x.get("size") or 0) for x in self.transfers[transfer_id]["files"])
            current = sum(int(x.get("done") or 0) for x in self.transfers[transfer_id]["files"])
            self._progress(transfer_id, current)

    def _set_transfer_status(self, transfer_id: str, status: str, error: str = "") -> dict[str, Any]:
        terminal = status in ("completed", "failed", "rejected", "cancelled")
        now = time.time()
        with self.lock:
            t = self.transfers.get(transfer_id)
            if not t:
                return {}
            t["status"] = status
            if error:
                t["error"] = str(error)[:1000]
            if terminal:
                t["finished_at"] = now
                started = float(t.get("started_at") or now)
                elapsed = max(0.001, now - started)
                total_bytes = int(t.get("total_bytes") or 0)
                done = total_bytes if status == "completed" else int(t.get("done_bytes") or 0)
                avg = (done / elapsed) if done > 0 else 0.0
                t["avg_speed"] = avg
                if status == "completed":
                    t["speed"] = avg
                    t["eta"] = 0
                else:
                    t["speed"] = avg
                    t["eta"] = None
                t["done_bytes"] = t.get("total_bytes", 0) if status == "completed" else t.get("done_bytes", 0)
                if t.get("entry_id"):
                    self.history.update(
                        t["entry_id"],
                        status=status,
                        error=t.get("error", ""),
                        finished_at=now,
                        files=[dict(f) for f in t.get("files", [])],
                        total_bytes=t.get("total_bytes", 0),
                    )
            public = self._public_transfer(t)
        return public

    def _finish_all_files(self, transfer_id: str) -> None:
        with self.lock:
            t = self.transfers.get(transfer_id)
            if not t:
                return
            if all(f.get("status") == "completed" for f in t.get("files", [])):
                self._set_transfer_status(transfer_id, "completed")

    def _prune_loop(self) -> None:
        while not self._stop.wait(60):
            try:
                self._prune()
            except Exception:
                LOG.debug("清理任务异常", exc_info=True)

    def _prune(self) -> None:
        now = time.time()
        with self.lock:
            sessions = list(self.sessions.values())
        for s in sessions:
            if s.status in ("completed", "cancelled", "rejected", "failed"):
                continue
            if now - s.updated > 86400:
                self._reject_session(s, "会话超时")
        with self.lock:
            for o in list(self.offers.values()):
                if o.status in ("pending", "accepted", "downloading") and now - o.updated > 86400:
                    o.status = "expired"
                    o.updated = now
                    t = self.transfers.get(o.transfer_id)
                    if t and t.get("status") not in ("completed", "rejected", "cancelled"):
                        self._set_transfer_status(o.transfer_id, "failed", "网页接收超时")
            # 长时间离线的网页会话会积累 token，清理掉（不影响在线页面）。
            for ws_id, ws in list(self.web_sessions.items()):
                if not ws.connected and now - ws.last_seen > 3600:
                    self.web_sessions.pop(ws_id, None)
            # 清理过旧的已完成传输
            if len(self.transfers) > 80:
                finished = sorted(
                    [t for t in self.transfers.values() if t.get("finished_at")],
                    key=lambda x: float(x.get("finished_at") or 0),
                )
                for t in finished[: max(0, len(self.transfers) - 60)]:
                    self.transfers.pop(t["id"], None)
                    self._speed_samples.pop(t["id"], None)
            old_tmp = now - 7 * 86400
            for directory in self.store.tmp_dir.glob("*"):
                try:
                    if directory.is_dir() and directory.stat().st_mtime < old_tmp:
                        shutil.rmtree(directory, ignore_errors=True)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # 接收：会话与确认
    # ------------------------------------------------------------------
    def _validate_files(self, raw_files: Any) -> list[dict[str, Any]]:
        if raw_files is None:
            return []
        if not isinstance(raw_files, list):
            raise ApiError(400, "files 必须是数组")
        if len(raw_files) > MAX_FILES:
            raise ApiError(400, f"文件数量超过上限 {MAX_FILES}")
        result: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        total = 0
        for item in raw_files:
            if not isinstance(item, dict):
                raise ApiError(400, "文件项格式错误")
            fid = str(item.get("id") or "")
            if not fid:
                fid = uuid.uuid4().hex
            if fid in seen_ids:
                raise ApiError(400, "文件 ID 重复")
            seen_ids.add(fid)
            name = sanitize_name(str(item.get("name") or "未命名文件"))
            rel_path = sanitize_rel_path(str(item.get("rel_path") or name), name)
            try:
                size = int(item.get("size") or 0)
            except (TypeError, ValueError):
                raise ApiError(400, "文件大小格式错误")
            if size < 0 or size > MAX_FILE_SIZE:
                raise ApiError(400, "文件大小超出范围")
            total += size
            if total > MAX_TOTAL_SIZE:
                raise ApiError(400, "传输总大小超出范围")
            result.append(
                {
                    "id": fid,
                    "name": name,
                    "rel_path": rel_path,
                    "size": size,
                }
            )
        free = shutil.disk_usage(self.config.download_dir).free
        if total > free - 200 * 1024 * 1024:
            raise ApiError(507, "接收目录磁盘空间不足")
        return result

    def _create_session(
        self,
        *,
        peer: dict[str, Any],
        files: list[dict[str, Any]],
        text: str,
        via: str,
        web_id: str = "",
        status: str = "waiting",
    ) -> IncomingSession:
        if not files and not text:
            raise ApiError(400, "没有要传输的内容")
        if len(text) > MAX_TEXT:
            raise ApiError(400, "文本内容过大")
        sid = uuid.uuid4().hex
        session = IncomingSession(
            id=sid,
            token=secrets.token_urlsafe(24),
            peer=dict(peer),
            via=via,
            web_id=web_id,
            files={},
            text=text,
            status=status,
            created=time.time(),
            updated=time.time(),
            transfer_id=sid,
            entry_id="",
        )
        part_dir = ensure_dir(self.store.tmp_dir / sid)
        transfer_files = []
        for idx, f in enumerate(files):
            file_id = str(f["id"])
            part_path = part_dir / f"{idx:05d}_{file_id}.part"
            token = secrets.token_urlsafe(24)
            item = IncomingFile(
                id=file_id,
                name=f["name"],
                rel_path=f["rel_path"],
                size=int(f["size"]),
                token=token,
                part_path=part_path,
            )
            session.files[file_id] = item
            transfer_files.append(
                {"id": file_id, "name": item.name, "rel_path": item.rel_path, "size": item.size}
            )
        transfer = self._new_transfer(
            direction="in",
            via=via,
            peer=peer,
            files=transfer_files,
            text=text,
            status=status,
            transfer_id=sid,
        )
        session.entry_id = transfer.get("entry_id", "")
        with self.lock:
            self.sessions[sid] = session
        return session

    def _tokens_for(self, session: IncomingSession) -> dict[str, str]:
        return {fid: f.token for fid, f in session.files.items()}

    def _accept_session(self, session: IncomingSession) -> None:
        with self.lock:
            if session.status not in ("waiting", "pending"):
                return
            session.status = "active"
            session.updated = time.time()
            self._set_transfer_status(session.transfer_id, "active")
        if session.text:
            self._save_incoming_text(session)
        if not session.files:
            self._complete_session(session)

    def _reject_session(self, session: IncomingSession, reason: str = "对方拒绝了传输") -> None:
        with self.lock:
            if session.status in ("completed", "rejected", "cancelled"):
                return
            session.status = "rejected"
            session.updated = time.time()
            self._set_transfer_status(session.transfer_id, "rejected", reason)
        for f in session.files.values():
            try:
                if f.part_path.exists():
                    f.part_path.unlink()
            except OSError:
                pass
        try:
            shutil.rmtree(self.store.tmp_dir / session.id, ignore_errors=True)
        except Exception:
            pass

    def _cancel_session(self, session: IncomingSession, reason: str = "已取消") -> None:
        """取消一个接收会话：关闭正在上传的连接，清理半成品。"""
        with self.lock:
            if session.status in ("completed", "cancelled", "rejected"):
                return
            session.cancel_requested = True
            session.status = "cancelled"
            session.updated = time.time()
            handlers = list(session.active_handlers)
            for pending in self.pending.values():
                if pending.session is session:
                    pending.decision = False
                    pending.event.set()
            self._set_transfer_status(session.transfer_id, "cancelled", reason)
        for handler in handlers:
            try:
                handler.close_connection = True
                handler.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                handler.connection.close()
            except OSError:
                pass
        for item in session.files.values():
            try:
                if item.part_path.exists():
                    item.part_path.unlink()
            except OSError:
                pass
        try:
            shutil.rmtree(self.store.tmp_dir / session.id, ignore_errors=True)
        except Exception:
            pass

    def _complete_session(self, session: IncomingSession) -> None:
        with self.lock:
            if session.status in ("completed", "rejected", "cancelled"):
                return
            session.status = "completed"
            session.updated = time.time()
        self._set_transfer_status(session.transfer_id, "completed")
        try:
            shutil.rmtree(self.store.tmp_dir / session.id, ignore_errors=True)
        except Exception:
            pass

    def _ask_accept(self, session: IncomingSession) -> bool:
        pid = uuid.uuid4().hex
        pending = PendingRequest(id=pid, session=session, created=time.time())
        with self.lock:
            self.pending[pid] = pending
        LOG.info("等待确认：%s 的传输", session.peer.get("alias"))
        accepted = pending.event.wait(timeout=max(10, int(self.config.request_timeout)))
        with self.lock:
            self.pending.pop(pid, None)
            if pending.decision is None:
                pending.decision = False
        if accepted and pending.decision:
            self._accept_session(session)
            return True
        if session.cancel_requested or session.status == "cancelled":
            self._cancel_session(session, "已取消")
            return False
        self._reject_session(session, "等待确认超时" if not accepted else "对方拒绝了传输")
        return False

    def list_pending(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                {
                    "id": p.id,
                    "session_id": p.session.id,
                    "peer": self._peer_public(p.session.peer),
                    "files": [
                        {"name": f.name, "rel_path": f.rel_path, "size": f.size}
                        for f in p.session.files.values()
                    ],
                    "text": p.session.text,
                    "created": p.created,
                    "expires_in": max(
                        0,
                        int(self.config.request_timeout - (time.time() - p.created)),
                    ),
                }
                for p in self.pending.values()
                if p.decision is None
            ]

    def decide_pending(self, pending_id: str, accept: bool) -> bool:
        with self.lock:
            p = self.pending.get(pending_id)
            if not p or p.decision is not None:
                return False
            p.decision = bool(accept)
            p.event.set()
            return True

    def _console_decision_loop(self) -> None:
        while not self._stop.is_set():
            pending = self.list_pending()
            if not pending:
                time.sleep(0.4)
                continue
            item = pending[0]
            peer = item["peer"].get("alias") or item["peer"].get("ip") or "未知设备"
            print("\n" + "=" * 60)
            print(f"收到来自 {peer} 的传输请求")
            for f in item["files"]:
                print(f"  - {f['rel_path']}  ({human_size(f['size'])})")
            if item["text"]:
                print(f"  文本：{item['text'][:200]}")
            print(f"请在 {item['expires_in']} 秒内确认")
            try:
                answer = input("接受? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            self.decide_pending(item["id"], answer not in ("n", "no", "拒绝"))
            time.sleep(0.2)

    def handle_peer_request(self, body: dict[str, Any], ip: str) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise ApiError(400, "请求格式错误")
        from_info = body.get("from") if isinstance(body.get("from"), dict) else {}
        peer_id = str(from_info.get("id") or "")
        if not peer_id:
            raise ApiError(400, "缺少发送方设备信息")
        if self.config.pin:
            if str(body.get("pin") or "") != self.config.pin:
                raise ApiError(403, "需要正确的 PIN 码", {"requires_pin": True})
        files = self._validate_files(body.get("files") or [])
        text = str(body.get("text") or "")
        alias = sanitize_name(str(from_info.get("alias") or "未知设备"))
        peer = {
            "id": peer_id,
            "alias": alias[:48],
            "device_type": str(from_info.get("device_type") or "desktop"),
            "version": str(from_info.get("version") or ""),
            "platform": str(from_info.get("platform") or ""),
            "fingerprint": str(from_info.get("fingerprint") or ""),
            "ip": ip,
            "port": int(from_info.get("port") or 0) or None,
        }
        self.remember_peer({**from_info, "id": peer_id, "alias": alias}, ip, peer["port"])
        session = self._create_session(peer=peer, files=files, text=text, via="peer")
        if self.config.auto_accept:
            self._accept_session(session)
        else:
            if not self._ask_accept(session):
                raise ApiError(403, "传输未被接受", {"accepted": False})
        return {
            "accepted": True,
            "session_id": session.id,
            "session_token": session.token,
            "tokens": self._tokens_for(session),
            "peer_alias": self.config.alias,
            "resume": {fid: 0 for fid in session.files},
            "auto_accepted": bool(self.config.auto_accept),
        }

    # ------------------------------------------------------------------
    # 接收：上传 / 完成 / 取消 / 状态
    # ------------------------------------------------------------------
    def _get_session(self, session_id: str) -> IncomingSession:
        with self.lock:
            session = self.sessions.get(session_id)
        if not session:
            raise ApiError(404, "传输会话不存在或已过期")
        return session

    def _check_file_token(self, session: IncomingSession, file_id: str, token: str) -> IncomingFile:
        f = session.files.get(file_id)
        if not f or not hmac.compare_digest(f.token, token):
            raise ApiError(403, "文件令牌无效")
        return f

    def handle_upload(self, handler: "AsterHandler", query: dict[str, list[str]]) -> dict[str, Any]:
        session_id = (query.get("session_id") or [""])[0]
        file_id = (query.get("file_id") or [""])[0]
        token = (query.get("token") or [""])[0]
        try:
            offset = int((query.get("offset") or ["0"])[0])
        except ValueError:
            raise ApiError(400, "offset 无效")
        session = self._get_session(session_id)
        f = self._check_file_token(session, file_id, token)
        if session.cancel_requested or session.status == "cancelled":
            raise ApiError(410, "传输已取消")
        if session.status != "active":
            raise ApiError(409, f"会话状态不可上传：{session.status}")
        with self.lock:
            if f.status == "completed":
                return {"received": f.size, "size": f.size, "complete": True, "already": True}
            if f.status == "verifying":
                raise ApiError(409, "文件正在校验，请调用 complete")
            if offset != f.received:
                raise ApiError(409, "偏移不匹配", {"received": f.received})
            try:
                length = int(handler.headers.get("Content-Length") or "0")
            except ValueError:
                raise ApiError(400, "Content-Length 无效")
            if length < 0 or f.received + length > f.size:
                raise ApiError(413, "上传长度超出声明大小", {"received": f.received})
            f.status = "uploading"
        with self.lock:
            session.active_handlers.add(handler)
        try:
            ensure_dir(f.part_path.parent)
            mode = "r+b" if offset > 0 else "wb"
            if offset > 0 and not f.part_path.exists():
                with self.lock:
                    f.received = 0
                    f.status = "pending"
                raise ApiError(409, "续传分片不存在，请从 0 开始", {"received": 0})
            remaining = length
            try:
                with open(f.part_path, mode) as fh:
                    if offset > 0:
                        fh.seek(offset)
                    while remaining > 0:
                        if session.cancel_requested:
                            raise ApiError(410, "传输已取消")
                        chunk = handler.rfile.read(min(256 * 1024, remaining))
                        if not chunk:
                            raise ConnectionError("客户端提前断开")
                        fh.write(chunk)
                        remaining -= len(chunk)
                        with self.lock:
                            f.received += len(chunk)
                            f.updated = time.time()
                            current = sum(x.received for x in session.files.values())
                        self._progress(session.transfer_id, current, f.name)
                    fh.flush()
            except (ConnectionError, BrokenPipeError, OSError) as exc:
                with self.lock:
                    cancelled = session.cancel_requested or session.status == "cancelled"
                    f.status = "cancelled" if cancelled else "pending"
                    session.updated = time.time()
                LOG.info("上传中断 %s：%s", f.name, exc)
                if cancelled:
                    raise ApiError(410, "传输已取消") from exc
                raise ApiError(400, "上传中断，可从断点继续", {"received": f.received}) from exc
            with self.lock:
                if session.cancel_requested or session.status == "cancelled":
                    f.status = "cancelled"
                    raise ApiError(410, "传输已取消")
                complete = f.received >= f.size
                if complete:
                    f.status = "verifying"
                    session.updated = time.time()
                    self._set_transfer_status(session.transfer_id, "verifying")
            if complete:
                self._progress(session.transfer_id, sum(x.received for x in session.files.values()), f.name)
            return {
                "received": f.received,
                "size": f.size,
                "complete": complete,
                "needs_verify": complete,
            }
        finally:
            with self.lock:
                session.active_handlers.discard(handler)
            if session.cancel_requested:
                try:
                    f.part_path.unlink(missing_ok=True)
                except OSError:
                    pass
                try:
                    shutil.rmtree(self.store.tmp_dir / session.id, ignore_errors=True)
                except Exception:
                    pass

    def handle_complete(self, body: dict[str, Any]) -> dict[str, Any]:
        session = self._get_session(str(body.get("session_id") or ""))
        file_id = str(body.get("file_id") or "")
        f = self._check_file_token(session, file_id, str(body.get("token") or ""))
        provided_sha = str(body.get("sha256") or "").strip().lower()
        with self.lock:
            if f.status == "completed":
                return {"ok": True, "name": f.name, "already": True}
            if f.received != f.size:
                raise ApiError(409, "文件尚未接收完整", {"received": f.received})
            if f.status == "finalizing":
                raise ApiError(409, "文件正在落盘")
            f.status = "finalizing"
        actual = ""
        try:
            if provided_sha:
                actual = sha256_file(f.part_path)
                if not hmac.compare_digest(actual, provided_sha):
                    with self.lock:
                        f.status = "pending"
                        f.received = 0
                        f.actual_sha256 = actual
                        f.error = "SHA-256 不匹配"
                    try:
                        f.part_path.unlink()
                    except OSError:
                        pass
                    raise ApiError(422, "SHA-256 校验失败，请重新发送该文件")
            rel = sanitize_rel_path(f.rel_path, f.name)
            target = safe_join(Path(self.config.download_dir), rel)
            ensure_dir(target.parent)
            target = unique_path(target)
            try:
                os.replace(f.part_path, target)
            except OSError:
                shutil.copy2(f.part_path, target)
                try:
                    f.part_path.unlink()
                except OSError:
                    pass
        except ApiError:
            raise
        except Exception as exc:
            with self.lock:
                f.status = "failed"
                f.error = str(exc)
            self._set_transfer_status(session.transfer_id, "failed", f"写入失败：{exc}")
            raise ApiError(500, f"写入文件失败：{exc}") from exc
        with self.lock:
            f.status = "completed"
            f.actual_sha256 = actual
            f.final_path = str(target)
            f.received = f.size
            session.updated = time.time()
            current = sum(x.received for x in session.files.values())
            self._set_file_status(session.transfer_id, f.id, "completed", f.size)
            self._progress(session.transfer_id, current, f.name)
            all_done = all(x.status == "completed" for x in session.files.values())
        if all_done:
            self._complete_session(session)
        return {
            "ok": True,
            "name": f.name,
            "sha256": actual,
            "path": f.name,
        }

    def handle_status(self, session_id: str, file_id: str, token: str) -> dict[str, Any]:
        session = self._get_session(session_id)
        f = self._check_file_token(session, file_id, token)
        with self.lock:
            return {
                "session_id": session.id,
                "file_id": f.id,
                "received": f.received,
                "size": f.size,
                "status": f.status,
                "session_status": session.status,
            }

    def handle_cancel(self, body: dict[str, Any]) -> dict[str, Any]:
        session = self._get_session(str(body.get("session_id") or ""))
        token = str(body.get("token") or "")
        if not hmac.compare_digest(session.token, token) and not any(
            hmac.compare_digest(f.token, token) for f in session.files.values()
        ):
            raise ApiError(403, "取消令牌无效")
        with self.lock:
            session.cancel_requested = True
            if session.status in ("completed", "cancelled", "rejected"):
                return {"ok": True, "status": session.status}
            session.status = "cancelled"
            session.updated = time.time()
            self._set_transfer_status(session.transfer_id, "cancelled", "发送方取消了传输")
        for f in session.files.values():
            try:
                if f.part_path.exists():
                    f.part_path.unlink()
            except OSError:
                pass
        return {"ok": True, "status": "cancelled"}

    def _save_incoming_text(self, session: IncomingSession) -> None:
        text = session.text
        if not text:
            return
        ok = set_clipboard_text(text)
        item = {
            "id": uuid.uuid4().hex,
            "text": text[:MAX_TEXT],
            "direction": "in",
            "peer": self._peer_public(session.peer),
            "created": time.time(),
            "via": session.via,
            "clipboard": ok,
        }
        with self.lock:
            self.texts.append(item)
        LOG.info("已接收文本（%s 字符），剪贴板=%s", len(text), ok)

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------
    def _peer_endpoint(
        self, peer: dict[str, Any], force_tls: Optional[bool] = None
    ) -> tuple[bool, int]:
        """按本机偏好、命令行强制项和对端能力选择 HTTP/HTTPS。"""
        if force_tls is True:
            https_port = int(peer.get("https_port") or 0)
            if 1024 <= https_port <= 65535:
                return True, https_port
        if force_tls is False:
            return False, int(peer.get("port") or self.port)
        if self.config.prefer_https and self.tls_material:
            https_port = int(peer.get("https_port") or 0)
            if 1024 <= https_port <= 65535:
                return True, https_port
        return False, int(peer.get("port") or self.port)

    def send_to_peer(
        self,
        peer: dict[str, Any],
        paths: list[str],
        *,
        text: str = "",
        pin: str = "",
        cancel_event: Optional[threading.Event] = None,
        force_tls: Optional[bool] = None,
    ) -> dict[str, Any]:
        if not paths and not text:
            raise ValueError("没有要发送的内容")
        files = expand_paths(paths) if paths else []
        peer_public = self._peer_public(peer)
        transfer = self._new_transfer(
            direction="out",
            via="peer",
            peer=peer,
            files=public_files(files),
            text=text,
            status="waiting",
        )
        tid = transfer["id"]
        event = cancel_event or threading.Event()
        with self.lock:
            self._cancel_events[tid] = event
        use_tls, target_port = self._peer_endpoint(peer, force_tls)
        client = PeerClient(
            str(peer.get("ip")),
            target_port,
            timeout=25,
            use_tls=use_tls,
        )
        session_id = ""
        session_token = ""
        tokens: dict[str, str] = {}
        try:
            if event.is_set():
                raise CancelledError()
            resp = client.request_transfer(
                self.device_info(),
                public_files(files),
                text=text,
                pin=pin,
                timeout=max(30, int(self.config.request_timeout) + 15),
            )
            session_id = str(resp.get("session_id") or "")
            session_token = str(resp.get("session_token") or "")
            tokens = {str(k): str(v) for k, v in (resp.get("tokens") or {}).items()}
            if not session_id or (files and len(tokens) != len(files)):
                raise PeerError(0, "对方返回的会话信息不完整")
            if event.is_set():
                raise CancelledError()
            self._set_transfer_status(tid, "active")
            for idx, f in enumerate(files):
                if event.is_set():
                    raise CancelledError()
                token = tokens.get(str(f["id"]))
                if not token:
                    raise PeerError(0, "缺少文件令牌")
                base = sum(int(x["size"]) for x in files[:idx])
                self._set_file_status(tid, str(f["id"]), "uploading", 0)
                self._upload_one(
                    client,
                    session_id,
                    session_token,
                    f,
                    token,
                    tid,
                    base,
                    event,
                )
                self._set_file_status(tid, str(f["id"]), "completed", int(f["size"]))
                self._progress(tid, base + int(f["size"]), f["name"])
            self._set_transfer_status(tid, "completed")
            return self._public_transfer(self.transfers[tid])
        except CancelledError:
            if session_id:
                try:
                    client.cancel(session_id, session_token or (next(iter(tokens.values())) if tokens else ""))
                except Exception:
                    pass
            self._set_transfer_status(tid, "cancelled", "已取消")
            return self._public_transfer(self.transfers[tid])
        except PeerError as exc:
            if session_id:
                try:
                    client.cancel(session_id, session_token or (next(iter(tokens.values())) if tokens else ""))
                except Exception:
                    pass
            status = "rejected" if exc.status == 403 else "failed"
            self._set_transfer_status(tid, status, exc.message)
            return self._public_transfer(self.transfers[tid])
        except Exception as exc:
            self._set_transfer_status(tid, "failed", f"发送失败：{exc}")
            return self._public_transfer(self.transfers.get(tid, {}))
        finally:
            with self.lock:
                self._cancel_events.pop(tid, None)

    def _upload_one(
        self,
        client: PeerClient,
        session_id: str,
        session_token: str,
        f: dict[str, Any],
        token: str,
        transfer_id: str,
        base: int,
        cancel_event: Optional[threading.Event],
    ) -> None:
        path = Path(f["path"])
        size = int(f["size"])
        received = 0
        try:
            status = client.get_status(session_id, str(f["id"]), token)
            received = int(status.get("received") or 0)
        except PeerError:
            received = 0
        if received >= size:
            sha = sha256_file(path)
            client.complete_file(session_id, str(f["id"]), token, sha)
            return
        self._progress(transfer_id, base + received, str(f["name"]))
        last_error: Optional[PeerError] = None
        for attempt in range(3):
            if cancel_event and cancel_event.is_set():
                raise CancelledError()
            try:
                data, sha = client.upload_file(
                    session_id,
                    str(f["id"]),
                    token,
                    path,
                    offset=received,
                    progress=lambda sent, total: self._progress(
                        transfer_id, base + sent, str(f["name"])
                    ),
                    cancel=lambda: bool(cancel_event and cancel_event.is_set()),
                )
                if sha is None:
                    sha = sha256_file(path)
                client.complete_file(session_id, str(f["id"]), token, sha)
                return
            except CancelledError:
                raise
            except PeerError as exc:
                last_error = exc
                if exc.status == 409:
                    with self.lock:
                        received = int((exc.data or {}).get("received", received))
                    if received >= size:
                        sha = sha256_file(path)
                        client.complete_file(session_id, str(f["id"]), token, sha)
                        return
                    continue
                if exc.status in (0, 408) and attempt < 2:
                    time.sleep(1.0)
                    try:
                        st = client.get_status(session_id, str(f["id"]), token)
                        received = int(st.get("received") or 0)
                        if received >= size:
                            sha = sha256_file(path)
                            client.complete_file(session_id, str(f["id"]), token, sha)
                            return
                    except PeerError:
                        pass
                    continue
                raise
        if last_error:
            raise last_error

    def send_to_web(
        self,
        web_id: str,
        paths: list[str],
        *,
        text: str = "",
    ) -> dict[str, Any]:
        with self.lock:
            ws = self.web_sessions.get(web_id)
        if not ws:
            raise ValueError("网页设备不存在或已断开")
        files = expand_paths(paths) if paths else []
        if not files and not text:
            raise ValueError("没有要发送的内容")
        offer_id = uuid.uuid4().hex
        offer_files = []
        for idx, f in enumerate(files):
            offer_files.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "rel_path": f["rel_path"],
                    "size": int(f["size"]),
                    "path": f["path"],
                    "sent": 0,
                    "status": "pending",
                }
            )
        transfer = self._new_transfer(
            direction="out",
            via="web",
            peer={
                "id": f"web:{ws.id}",
                "alias": ws.name,
                "device_type": "web",
                "client": ws.client,
                "ip": ws.ip,
                "port": 0,
            },
            files=public_files(files),
            text=text,
            status="pending",
        )
        offer = WebOffer(
            id=offer_id,
            web_id=ws.id,
            files=offer_files,
            text=text,
            status="pending",
            created=time.time(),
            updated=time.time(),
            entry_id=transfer.get("entry_id", ""),
            transfer_id=transfer["id"],
        )
        with self.lock:
            self.offers[offer_id] = offer
        return {
            "transfer": self._public_transfer(transfer),
            "offer": self._public_offer(offer, include_urls=True),
            "web": {"id": ws.id, "name": ws.name},
        }

    # ------------------------------------------------------------------
    # Web 配对与会话
    # ------------------------------------------------------------------
    def _rate_limit_pair(self, ip: str) -> None:
        now = time.time()
        with self.lock:
            attempts = [t for t in self._pair_attempts.get(ip, []) if now - t < 60]
            if len(attempts) >= 8:
                raise ApiError(429, "配对尝试过于频繁，请等一分钟")
            attempts.append(now)
            self._pair_attempts[ip] = attempts

    def pair_web(
        self, code: str, name: str, ua: str, ip: str, client: str = "web"
    ) -> dict[str, Any]:
        self._rate_limit_pair(ip)
        if self.config.web_pairing and not hmac.compare_digest(
            str(code or ""), str(self.config.web_pair_code)
        ):
            raise ApiError(403, "配对码错误")
        client = "apk" if str(client or "").lower() == "apk" else "web"
        fallback = "手机" if client == "apk" else "网页端设备"
        token = secrets.token_urlsafe(32)
        ws = WebSession(
            id=uuid.uuid4().hex,
            name=sanitize_name(str(name or fallback))[:40],
            ua=str(ua or "")[:300],
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            created=time.time(),
            last_seen=time.time(),
            ip=ip,
            client=client,
            connected=False,
        )
        with self.lock:
            if len(self.web_sessions) >= 24:
                oldest = sorted(self.web_sessions.values(), key=lambda w: w.last_seen)[:4]
                for old in oldest:
                    self.web_sessions.pop(old.id, None)
            self.web_sessions[ws.id] = ws
        LOG.info("网页设备已配对：%s (%s)", ws.name, ip)
        return {
            "token": token,
            "web_id": ws.id,
            "web": {"id": ws.id, "name": ws.name, "client": ws.client},
            "device": self.device_info(),
            "state": self.web_state(ws),
        }

    def auth_web(self, token: str) -> Optional[WebSession]:
        if not token:
            return None
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()
        with self.lock:
            for ws in self.web_sessions.values():
                if hmac.compare_digest(ws.token_hash, digest):
                    ws.last_seen = now
                    return ws
        return None

    def create_web_session(
        self, ws: WebSession, files_payload: Any, text: str = "", ip: str = ""
    ) -> dict[str, Any]:
        files = self._validate_files(files_payload or [])
        text = str(text or "")
        peer = {
            "id": f"web:{ws.id}",
            "alias": ws.name,
            "device_type": "web",
            "client": ws.client,
            "version": VERSION,
            "platform": ws.ua.split(")")[0][:60] if ws.ua else "Web",
            "ip": ip or ws.ip,
            "port": 0,
        }
        session = self._create_session(peer=peer, files=files, text=text, via="web", web_id=ws.id)
        self._accept_session(session)
        return {
            "accepted": True,
            "session_id": session.id,
            "session_token": session.token,
            "tokens": self._tokens_for(session),
            "resume": {fid: 0 for fid in session.files},
        }

    def receive_web_text(self, ws: WebSession, text: str) -> dict[str, Any]:
        text = str(text or "")
        if not text.strip():
            raise ApiError(400, "文本为空")
        if len(text) > MAX_TEXT:
            raise ApiError(413, "文本过大")
        peer = {
            "id": f"web:{ws.id}",
            "alias": ws.name,
            "device_type": "web",
            "client": ws.client,
            "ip": ws.ip,
            "port": 0,
        }
        transfer = self._new_transfer(
            direction="in",
            via="web",
            peer=peer,
            files=[],
            text=text,
            status="active",
        )
        ok = set_clipboard_text(text)
        with self.lock:
            self.texts.append(
                {
                    "id": uuid.uuid4().hex,
                    "text": text,
                    "direction": "in",
                    "peer": self._peer_public(peer),
                    "created": time.time(),
                    "via": "web",
                    "clipboard": ok,
                }
            )
        self._set_transfer_status(transfer["id"], "completed")
        return {"ok": True, "clipboard": ok, "transfer": self._public_transfer(transfer)}

    def respond_offer(self, ws: WebSession, offer_id: str, accept: bool) -> dict[str, Any]:
        with self.lock:
            offer = self.offers.get(offer_id)
            if not offer or offer.web_id != ws.id:
                raise ApiError(404, "接收请求不存在")
            if offer.status == "rejected":
                return {"ok": True, "status": "rejected"}
            if accept:
                offer.status = "accepted"
                offer.updated = time.time()
                self._offer_cancel.setdefault(offer.id, threading.Event()).clear()
                self._set_transfer_status(offer.transfer_id, "active")
                text_only = not offer.files
            else:
                offer.status = "rejected"
                offer.updated = time.time()
                self._offer_cancel.setdefault(offer.id, threading.Event()).set()
                self._set_transfer_status(offer.transfer_id, "rejected", "手机端拒绝了接收")
                text_only = False
        if accept and text_only:
            with self.lock:
                self.texts.append(
                    {
                        "id": uuid.uuid4().hex,
                        "text": offer.text,
                        "direction": "out",
                        "peer": {
                            "id": f"web:{ws.id}",
                            "alias": ws.name,
                            "device_type": "web",
                            "client": ws.client,
                        },
                        "created": time.time(),
                        "via": "web",
                    }
                )
                offer.status = "completed"
            self._set_transfer_status(offer.transfer_id, "completed")
        return {"ok": True, "status": offer.status}

    def cancel_offer_download(self, ws: WebSession, offer_id: str) -> dict[str, Any]:
        """手机端在下载过程中取消；关闭正在写文件的连接，避免继续占带宽。"""
        sockets: list[Any] = []
        with self.lock:
            offer = self.offers.get(offer_id)
            if not offer or offer.web_id != ws.id:
                raise ApiError(404, "下载请求不存在")
            if offer.status == "completed":
                return {"ok": True, "status": "completed"}
            event = self._offer_cancel.setdefault(offer.id, threading.Event())
            event.set()
            offer.status = "cancelled"
            offer.updated = time.time()
            sockets = list(self._offer_sockets.get(offer.id, set()))
            self._set_transfer_status(offer.transfer_id, "cancelled", "已在手机端取消下载")
        for conn in sockets:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
        return {"ok": True, "status": "cancelled"}

    # ------------------------------------------------------------------
    # 任务取消 / 网页设备命名 / 检查更新
    # ------------------------------------------------------------------
    def cancel_transfer(self, transfer_id: str) -> dict[str, Any]:
        """按任务 ID 取消；覆盖发送、接收、网页 offer 和等待确认。"""
        tid = str(transfer_id or "")
        with self.lock:
            transfer = self.transfers.get(tid)
            if not transfer:
                raise ValueError("任务不存在或已结束")
            status = str(transfer.get("status") or "")
            if status not in ACTIVE_TRANSFER_STATUSES:
                return self._public_transfer(transfer)
            event = self._cancel_events.get(tid)
            if event is not None:
                event.set()
            offer = next((o for o in self.offers.values() if o.transfer_id == tid), None)
            session = self.sessions.get(tid)
            if session is None:
                session = next(
                    (s for s in self.sessions.values() if s.transfer_id == tid), None
                )
        if offer is not None:
            sockets: list[Any] = []
            with self.lock:
                offer.status = "cancelled"
                offer.updated = time.time()
                self._offer_cancel.setdefault(offer.id, threading.Event()).set()
                sockets = list(self._offer_sockets.get(offer.id, set()))
            for conn in sockets:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    conn.close()
                except OSError:
                    pass
            self._set_transfer_status(tid, "cancelled", "已取消")
        elif session is not None:
            self._cancel_session(session, "已取消")
        else:
            self._set_transfer_status(tid, "cancelled", "已取消")
        with self.lock:
            transfer = self.transfers.get(tid) or {}
            return self._public_transfer(transfer)

    def cancel_all_transfers(self) -> list[dict[str, Any]]:
        with self.lock:
            ids = [
                tid
                for tid, transfer in self.transfers.items()
                if str(transfer.get("status") or "") in ACTIVE_TRANSFER_STATUSES
            ]
        results: list[dict[str, Any]] = []
        for tid in ids:
            try:
                results.append(self.cancel_transfer(tid))
            except Exception:
                LOG.debug("取消任务失败：%s", tid, exc_info=True)
        return results

    def _web_owns_transfer(self, ws: WebSession, transfer_id: str) -> bool:
        tid = str(transfer_id or "")
        peer_id = f"web:{ws.id}"
        with self.lock:
            if any(o.transfer_id == tid and o.web_id == ws.id for o in self.offers.values()):
                return True
            if any(
                s.transfer_id == tid and s.web_id == ws.id
                for s in self.sessions.values()
            ):
                return True
            transfer = self.transfers.get(tid)
            if transfer and str((transfer.get("peer") or {}).get("id") or "") == peer_id:
                return True
        return False

    def cancel_web_transfer(self, ws: WebSession, transfer_id: str) -> dict[str, Any]:
        if not self._web_owns_transfer(ws, transfer_id):
            raise ApiError(403, "这个任务不属于当前网页设备")
        try:
            return self.cancel_transfer(transfer_id)
        except ValueError as exc:
            raise ApiError(404, str(exc)) from exc

    def cancel_web_transfers(self, ws: WebSession) -> list[dict[str, Any]]:
        with self.lock:
            ids: set[str] = set()
            peer_id = f"web:{ws.id}"
            for tid, transfer in self.transfers.items():
                if str(transfer.get("status") or "") not in ACTIVE_TRANSFER_STATUSES:
                    continue
                if str((transfer.get("peer") or {}).get("id") or "") == peer_id:
                    ids.add(tid)
            for offer in self.offers.values():
                if offer.web_id == ws.id:
                    transfer = self.transfers.get(offer.transfer_id) or {}
                    if str(transfer.get("status") or "") in ACTIVE_TRANSFER_STATUSES:
                        ids.add(offer.transfer_id)
            for session in self.sessions.values():
                if session.web_id == ws.id:
                    transfer = self.transfers.get(session.transfer_id) or {}
                    if str(transfer.get("status") or "") in ACTIVE_TRANSFER_STATUSES:
                        ids.add(session.transfer_id)
        results: list[dict[str, Any]] = []
        for tid in ids:
            try:
                results.append(self.cancel_transfer(tid))
            except Exception:
                LOG.debug("取消网页任务失败：%s", tid, exc_info=True)
        return results

    def rename_web_session(self, ws: WebSession, name: str) -> dict[str, Any]:
        cleaned = sanitize_name(str(name or "")).strip()[:40]
        if not cleaned:
            raise ApiError(400, "设备名称不能为空")
        peer_id = f"web:{ws.id}"
        with self.lock:
            ws.name = cleaned
            ws.last_seen = time.time()
            for transfer in self.transfers.values():
                peer = transfer.get("peer") or {}
                if str(peer.get("id") or "") == peer_id:
                    peer["alias"] = cleaned
            for session in self.sessions.values():
                if session.web_id == ws.id:
                    session.peer["alias"] = cleaned
        LOG.info("网页设备已改名：%s", cleaned)
        return {"ok": True, "web": {"id": ws.id, "name": cleaned, "client": ws.client}}

    def check_update(self, force: bool = False) -> dict[str, Any]:
        return update_mod.check_update(force=force)

    def serve_offer_download(
        self,
        handler: "AsterHandler",
        ws: WebSession,
        offer_id: str,
        file_id: str,
        range_header: str = "",
        head: bool = False,
    ) -> None:
        with self.lock:
            offer = self.offers.get(offer_id)
            if not offer or offer.web_id != ws.id:
                raise ApiError(404, "文件不存在")
            if offer.status == "rejected":
                raise ApiError(403, "接收请求已被拒绝")
            f = next((x for x in offer.files if x["id"] == file_id), None)
            if not f:
                raise ApiError(404, "文件不存在")
            cancel_event = self._offer_cancel.setdefault(offer.id, threading.Event())
            if offer.status == "rejected" or cancel_event.is_set():
                raise ApiError(410, "下载已取消")
            if offer.status == "pending":
                offer.status = "accepted"
                offer.updated = time.time()
                self._set_transfer_status(offer.transfer_id, "active")
        path = Path(f["path"])
        if not path.is_file():
            raise ApiError(404, "源文件已不存在")
        size = int(f["size"])
        start, end = 0, size - 1
        status = 200
        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
            if not m:
                raise ApiError(416, "Range 无效")
            if m.group(1):
                start = int(m.group(1))
            if m.group(2):
                end = int(m.group(2))
            if start < 0 or start >= size or end < start:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{size}")
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            end = min(end, size - 1)
            status = 206
        length = end - start + 1
        ctype = mimetypes.guess_type(f["name"])[0] or "application/octet-stream"
        ascii_name = f["name"].encode("ascii", "ignore").decode("ascii") or "download"
        disposition = (
            f"attachment; filename=\"{ascii_name}\"; "
            f"filename*=UTF-8''{quote(f['name'])}"
        )
        handler.send_response(status)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Content-Length", str(length))
        handler.send_header("Content-Disposition", disposition)
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Cache-Control", "no-store")
        if status == 206:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        handler.end_headers()
        if head:
            return
        sock = getattr(handler, "connection", None)
        if sock is not None:
            with self.lock:
                self._offer_sockets.setdefault(offer.id, set()).add(sock)
        sent = 0
        cancelled = False
        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    if cancel_event.is_set():
                        cancelled = True
                        break
                    chunk = fh.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    handler.wfile.flush()
                    sent += len(chunk)
                    remaining -= len(chunk)
                    with self.lock:
                        f["sent"] = max(int(f.get("sent") or 0), start + sent)
                        if offer.status in ("accepted", "pending"):
                            offer.status = "downloading"
                        offer.updated = time.time()
                        current = sum(int(x.get("sent") or 0) for x in offer.files)
                        total = sum(int(x.get("size") or 0) for x in offer.files)
                    self._progress(offer.transfer_id, current, f["name"])
        except (BrokenPipeError, ConnectionResetError, OSError):
            if not cancel_event.is_set():
                return
            cancelled = True
        finally:
            if sock is not None:
                with self.lock:
                    sockets = self._offer_sockets.get(offer.id)
                    if sockets is not None:
                        sockets.discard(sock)
                        if not sockets:
                            self._offer_sockets.pop(offer.id, None)
        if cancelled:
            with self.lock:
                offer.status = "cancelled"
                offer.updated = time.time()
                self._set_transfer_status(offer.transfer_id, "cancelled", "已在手机端取消下载")
            return
        if start + sent >= size:
            with self.lock:
                f["status"] = "completed"
                f["sent"] = size
                if all(int(x.get("sent") or 0) >= int(x.get("size") or 0) for x in offer.files):
                    offer.status = "completed"
                    offer.updated = time.time()
                    all_done = True
                else:
                    all_done = False
                if all_done:
                    self._offer_cancel.pop(offer.id, None)
            if all_done:
                self._set_transfer_status(offer.transfer_id, "completed")

    def serve_events(self, handler: "AsterHandler", ws: WebSession) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "close")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()
        try:
            handler.wfile.write(b"retry: 2000\n\n")
            handler.wfile.flush()
        except OSError:
            return
        with self.lock:
            ws.connected = True
        try:
            while self.running:
                state = self.web_state(ws)
                payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
                try:
                    handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
                with self.lock:
                    ws.last_seen = time.time()
                time.sleep(1.0)
        finally:
            with self.lock:
                ws.connected = False

    # ------------------------------------------------------------------
    # 网页设置
    # ------------------------------------------------------------------
    def update_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        if "auto_accept" in body:
            self.set_auto_accept(bool(body.get("auto_accept")))
        if "prefer_https" in body:
            self.set_prefer_https(bool(body.get("prefer_https")))
        if "alias" in body:
            self.set_alias(str(body.get("alias") or ""))
        return self.snapshot(include_all_offers=False)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def public_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.history.list(limit)


# ---------------------------------------------------------------------------
# HTTP 服务
# ---------------------------------------------------------------------------


class AsterHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # 不能复用端口：Windows 上 SO_REUSEADDR 会让第二个实例也绑定成功，
    # 导致两个 Aster 抢同一个端口。这里要明确报“端口被占用”。
    allow_reuse_address = False
    allow_reuse_port = False
    node: AsterNode


class AsterHandler(BaseHTTPRequestHandler):
    server_version = f"Aster/{VERSION}"
    sys_version = ""

    @property
    def node(self) -> AsterNode:
        return self.server.node  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.debug("%s - %s", self.client_address[0], fmt % args)

    # ------------------------------------------------------------------
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, POST, HEAD, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path == "/favicon.ico":
                self._serve_static("/icons/icon-192.png", head=(method == "HEAD"))
            elif path.startswith("/api/"):
                self._handle_api(method, path, query)
            elif method in ("GET", "HEAD"):
                self._serve_static(path, head=(method == "HEAD"))
            else:
                raise ApiError(405, "方法不允许")
        except ApiError as exc:
            data = {"error": exc.message}
            data.update(exc.data or {})
            self._send_json(data, exc.status)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:
            LOG.exception("请求处理失败 %s %s", method, path)
            self._send_json({"error": f"服务器内部错误：{exc}"}, 500)

    # ------------------------------------------------------------------
    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            raise ApiError(400, "Content-Length 无效")
        if length < 0 or length > MAX_JSON_BODY:
            raise ApiError(413, "请求体过大")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "JSON 格式错误")
        if not isinstance(data, dict):
            raise ApiError(400, "请求体必须是对象")
        return data

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            self.close_connection = True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def _web_token(self, query: dict[str, list[str]], *, allow_query: bool = True) -> Optional[WebSession]:
        token = self.headers.get("X-Aster-Web-Token") or ""
        if not token:
            auth = self.headers.get("Authorization") or ""
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        if not token and allow_query:
            token = (query.get("token") or [""])[0]
        return self.node.auth_web(token)

    def _require_web(self, query: dict[str, list[str]], *, allow_query: bool = True) -> WebSession:
        ws = self._web_token(query, allow_query=allow_query)
        if not ws:
            raise ApiError(401, "网页会话已失效，请重新配对")
        return ws

    # ------------------------------------------------------------------
    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        node = self.node

        # -- 公共设备 API ------------------------------------------------
        if method == "GET" and path == "/api/v1/ping":
            self._send_json(
                {
                    "app": APP_NAME,
                    "ok": True,
                    "name": node.config.alias,
                    "version": VERSION,
                    "protocol": PROTOCOL_VERSION,
                    "time": time.time(),
                }
            )
            return
        if method == "GET" and path == "/api/v1/info":
            info = node.device_info()
            info["web_pairing"] = bool(node.config.web_pairing)
            info["auto_accept"] = bool(node.config.auto_accept)
            self._send_json(info)
            return
        if method == "GET" and path == "/api/v1/peers":
            self._send_json({"peers": node.list_peers()})
            return
        if method == "GET" and path == "/api/v1/history":
            self._require_web(query)
            self._send_json({"history": node.public_history(100)})
            return
        if method == "POST" and path == "/api/v1/hello":
            body = self._read_json()
            device = body.get("device") if isinstance(body.get("device"), dict) else body
            peer = node.remember_peer(device, self.client_address[0])
            self._send_json({"ok": True, "device": node.device_info(), "peer": node._peer_public(peer)})
            return

        # -- 对等传输 ----------------------------------------------------
        if method == "POST" and path == "/api/v1/transfer/request":
            body = self._read_json()
            result = node.handle_peer_request(body, self.client_address[0])
            self._send_json(result)
            return
        if method == "GET" and path == "/api/v1/transfer/status":
            q = {k: (v[0] if v else "") for k, v in query.items()}
            result = node.handle_status(
                str(q.get("session_id") or ""),
                str(q.get("file_id") or ""),
                str(q.get("token") or ""),
            )
            self._send_json(result)
            return
        if method == "POST" and path == "/api/v1/transfer/upload":
            result = node.handle_upload(self, query)
            self._send_json(result)
            return
        if method == "POST" and path == "/api/v1/transfer/complete":
            result = node.handle_complete(self._read_json())
            self._send_json(result)
            return
        if method == "POST" and path == "/api/v1/transfer/cancel":
            result = node.handle_cancel(self._read_json())
            self._send_json(result)
            return

        # -- 检查更新（不需要网页配对） ---------------------------------
        if method == "GET" and path == "/api/v1/update":
            force = (query.get("force") or [""])[0] in ("1", "true", "yes")
            self._send_json(node.check_update(force=force))
            return

        # -- 网页配对 ----------------------------------------------------
        if method == "POST" and path == "/api/v1/web/pair":
            body = self._read_json()
            ua = str(body.get("ua") or self.headers.get("User-Agent") or "")
            result = node.pair_web(
                str(body.get("code") or ""),
                str(body.get("name") or ""),
                ua,
                self.client_address[0],
                str(body.get("client") or "web"),
            )
            self._send_json(result)
            return

        # -- 网页 API（需要 token） -------------------------------------
        if method == "GET" and path == "/api/v1/web/state":
            ws = self._require_web(query)
            self._send_json(node.web_state(ws))
            return
        if method == "GET" and path == "/api/v1/web/events":
            ws = self._require_web(query)
            node.serve_events(self, ws)
            return
        if method == "POST" and path == "/api/v1/web/request":
            ws = self._require_web(query)
            body = self._read_json()
            result = node.create_web_session(
                ws, body.get("files") or [], str(body.get("text") or ""), self.client_address[0]
            )
            self._send_json(result)
            return
        if method == "POST" and path == "/api/v1/web/text":
            ws = self._require_web(query)
            body = self._read_json()
            result = node.receive_web_text(ws, str(body.get("text") or ""))
            self._send_json(result)
            return
        if method == "POST" and path == "/api/v1/web/settings":
            self._require_web(query)
            body = self._read_json()
            self._send_json(node.update_settings(body))
            return
        if method == "POST" and path == "/api/v1/web/name":
            ws = self._require_web(query)
            body = self._read_json()
            self._send_json(node.rename_web_session(ws, str(body.get("name") or "")))
            return
        if method == "POST" and path == "/api/v1/web/transfers/cancel-all":
            ws = self._require_web(query)
            self._send_json({"ok": True, "cancelled": node.cancel_web_transfers(ws)})
            return

        m = re.match(r"^/api/v1/web/transfers/([0-9a-zA-Z_-]+)/cancel$", path)
        if method == "POST" and m:
            ws = self._require_web(query)
            self._send_json({"ok": True, "transfer": node.cancel_web_transfer(ws, m.group(1))})
            return

        m = re.match(r"^/api/v1/web/offers/([0-9a-f]+)/respond$", path)
        if method == "POST" and m:
            ws = self._require_web(query)
            body = self._read_json()
            self._send_json(node.respond_offer(ws, m.group(1), bool(body.get("accept"))))
            return

        m = re.match(r"^/api/v1/web/offers/([0-9a-f]+)/cancel$", path)
        if method == "POST" and m:
            ws = self._require_web(query)
            self._send_json(node.cancel_offer_download(ws, m.group(1)))
            return

        m = re.match(
            r"^/api/v1/web/offers/([0-9a-f]+)/files/([0-9a-fA-F]+)/download$", path
        )
        if method in ("GET", "HEAD") and m:
            ws = self._require_web(query)
            node.serve_offer_download(
                self,
                ws,
                m.group(1),
                m.group(2),
                self.headers.get("Range") or "",
                head=(method == "HEAD"),
            )
            return

        raise ApiError(404, "接口不存在")

    # ------------------------------------------------------------------
    def _serve_static(self, path: str, *, head: bool = False) -> None:
        root = webui_path()
        if path in ("", "/"):
            rel = "index.html"
        else:
            rel = path.lstrip("/")
        if rel == "favicon.ico":
            rel = "icons/icon-192.png"
        try:
            target = (root / rel).resolve()
            if os.path.commonpath([str(root.resolve()), str(target)]) != str(root.resolve()):
                raise ApiError(404, "文件不存在")
        except ValueError:
            raise ApiError(404, "文件不存在")
        if not target.is_file():
            if rel == "index.html":
                raise ApiError(404, "网页界面文件缺失，请重新安装")
            raise ApiError(404, "文件不存在")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".webmanifest":
            ctype = "application/manifest+json"
        if target.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif target.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif target.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if rel in ("index.html", "sw.js") else "max-age=3600")
        self.send_header("X-Content-Type-Options", "nosniff")
        if rel == "sw.js":
            self.send_header("Service-Worker-Allowed", "/")
        self.end_headers()
        if not head:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
