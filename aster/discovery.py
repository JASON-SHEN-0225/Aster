"""局域网设备发现：UDP 多播 + 广播 + 单播探测。"""

from __future__ import annotations

import json
import logging
import socket
import struct
import threading
import time
from typing import Any, Callable, Optional

from . import APP_NAME, MULTICAST_GROUP, PROTOCOL_VERSION, VERSION
from .util import get_interface_ips

LOG = logging.getLogger("aster.discovery")

ANNOUNCE_INTERVAL = 4.0
PEER_ONLINE_WINDOW = 13.0
PEER_KEEP_WINDOW = 3600.0


class DiscoveryService:
    def __init__(
        self,
        device_provider: Callable[[], dict[str, Any]],
        port: int,
        *,
        enabled: bool = True,
        on_change: Optional[Callable[[], None]] = None,
    ):
        self.device_provider = device_provider
        self.port = int(port)
        self.enabled = enabled
        self.on_change = on_change
        self.peers: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._threads: list[threading.Thread] = []
        self._last_notify = 0.0
        self._joined = False
        self.error = ""

    # ------------------------------------------------------------------
    def start(self) -> bool:
        if not self.enabled:
            LOG.info("设备发现已禁用")
            return False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except OSError:
                pass
            sock.bind(("", self.port))
            sock.settimeout(0.6)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            except OSError:
                pass
            self._sock = sock
            self._join_multicast()
            self._threads = [
                threading.Thread(target=self._rx_loop, name="aster-discovery-rx", daemon=True),
                threading.Thread(target=self._announce_loop, name="aster-discovery-tx", daemon=True),
                threading.Thread(target=self._housekeeping, name="aster-discovery-house", daemon=True),
            ]
            for th in self._threads:
                th.start()
            self.send_query()
            self.send_announce()
            LOG.info("设备发现已启动：%s:%s", MULTICAST_GROUP, self.port)
            return True
        except OSError as exc:
            self.error = str(exc)
            LOG.warning("设备发现启动失败：%s", exc)
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
            return False

    def _join_multicast(self) -> None:
        assert self._sock
        group = socket.inet_aton(MULTICAST_GROUP)
        joined_any = False
        for ip in get_interface_ips():
            try:
                mreq = struct.pack("4s4s", group, socket.inet_aton(ip))
                self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                joined_any = True
                LOG.debug("加入多播：%s @ %s", MULTICAST_GROUP, ip)
            except OSError as exc:
                LOG.debug("加入多播失败 %s：%s", ip, exc)
        if not joined_any:
            try:
                mreq = struct.pack("4s4s", group, socket.inet_aton("0.0.0.0"))
                self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                joined_any = True
            except OSError as exc:
                LOG.debug("加入默认多播失败：%s", exc)
        self._joined = joined_any

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self.send_bye()
            except Exception:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        for th in self._threads:
            if th.is_alive():
                th.join(timeout=1.0)
        self._threads = []

    # ------------------------------------------------------------------
    def _device_payload(self, kind: str) -> bytes:
        device = self.device_provider()
        msg = {
            "app": APP_NAME.lower(),
            "protocol": PROTOCOL_VERSION,
            "version": VERSION,
            "type": kind,
            "device": device,
        }
        return json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _send(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self._sock:
            return
        try:
            self._sock.sendto(data, addr)
        except OSError as exc:
            LOG.debug("发送发现包失败 %s：%s", addr, exc)

    def send_announce(self, addr: Optional[tuple[str, int]] = None) -> None:
        data = self._device_payload("announce")
        if addr:
            self._send(data, addr)
            return
        self._send(data, (MULTICAST_GROUP, self.port))
        try:
            self._send(data, ("255.255.255.255", self.port))
        except OSError:
            pass

    def send_query(self, addr: Optional[tuple[str, int]] = None) -> None:
        data = self._device_payload("query")
        if addr:
            self._send(data, addr)
            return
        self._send(data, (MULTICAST_GROUP, self.port))
        try:
            self._send(data, ("255.255.255.255", self.port))
        except OSError:
            pass

    def send_bye(self) -> None:
        data = self._device_payload("bye")
        self._send(data, (MULTICAST_GROUP, self.port))
        try:
            self._send(data, ("255.255.255.255", self.port))
        except OSError:
            pass

    def probe(self, host: str, port: Optional[int] = None) -> bool:
        """向指定地址发一个查询，稍后由接收循环更新。"""
        target_port = int(port or self.port)
        try:
            data = self._device_payload("query")
            if self._sock:
                self._send(data, (host, target_port))
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(1.0)
                s.sendto(data, (host, target_port))
                s.close()
            return True
        except OSError as exc:
            LOG.debug("探测 %s:%s 失败：%s", host, target_port, exc)
            return False

    # ------------------------------------------------------------------
    def _rx_loop(self) -> None:
        assert self._sock
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    break
                time.sleep(0.2)
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            if not isinstance(msg, dict):
                continue
            if str(msg.get("app", "")).lower() != APP_NAME.lower():
                continue
            kind = msg.get("type")
            device = msg.get("device")
            if not isinstance(device, dict):
                continue
            if device.get("id") == self.device_provider().get("id"):
                continue
            if kind == "bye":
                self._remove(device.get("id"))
                continue
            if kind not in ("announce", "query"):
                continue
            self._upsert(device, addr)
            if kind == "query":
                try:
                    reply_port = int(device.get("port") or self.port)
                except (TypeError, ValueError):
                    reply_port = self.port
                self.send_announce((addr[0], reply_port))

    def _upsert(self, device: dict[str, Any], addr: tuple[str, int]) -> None:
        peer_id = str(device.get("id") or "")
        if not peer_id:
            return
        try:
            port = int(device.get("port") or self.port)
        except (TypeError, ValueError):
            port = self.port
        now = time.time()
        with self._lock:
            old = self.peers.get(peer_id)
            peer = dict(device)
            peer["ip"] = addr[0]
            peer["port"] = port
            peer["last_seen"] = now
            peer["online"] = True
            peer["device_type"] = peer.get("device_type") or "desktop"
            if old:
                # 保留首次发现的地址，除非对端端口变化
                peer["first_seen"] = old.get("first_seen", now)
            else:
                peer["first_seen"] = now
            self.peers[peer_id] = peer
        self._notify(force=old is None)

    def _remove(self, peer_id: Any) -> None:
        if not peer_id:
            return
        with self._lock:
            existed = self.peers.pop(str(peer_id), None)
        if existed:
            self._notify(force=True)

    def _announce_loop(self) -> None:
        beats = 0
        while not self._stop.wait(ANNOUNCE_INTERVAL):
            self.send_announce()
            beats += 1
            if beats % 3 == 0:
                self.send_query()

    def _housekeeping(self) -> None:
        while not self._stop.wait(2.0):
            now = time.time()
            changed = False
            with self._lock:
                for peer_id, peer in list(self.peers.items()):
                    online = (now - float(peer.get("last_seen") or 0)) <= PEER_ONLINE_WINDOW
                    if peer.get("online") != online:
                        peer["online"] = online
                        changed = True
                    if now - float(peer.get("last_seen") or 0) > PEER_KEEP_WINDOW:
                        self.peers.pop(peer_id, None)
                        changed = True
            if changed:
                self._notify(force=True)

    def _notify(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_notify < 0.5:
            return
        self._last_notify = now
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                LOG.debug("发现回调异常", exc_info=True)

    # ------------------------------------------------------------------
    def list_peers(self, include_offline: bool = True) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            result = []
            for peer in self.peers.values():
                item = dict(peer)
                item["online"] = (now - float(item.get("last_seen") or 0)) <= PEER_ONLINE_WINDOW
                if item["online"] or include_offline:
                    result.append(item)
        result.sort(key=lambda p: (not p.get("online"), str(p.get("alias", "")).lower()))
        return result

    def get_peer(self, peer_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            peer = self.peers.get(peer_id)
            if not peer:
                return None
            item = dict(peer)
            item["online"] = (time.time() - float(item.get("last_seen") or 0)) <= PEER_ONLINE_WINDOW
            return item

    def find(self, query: str) -> list[dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return []
        peers = self.list_peers()
        exact = [
            p
            for p in peers
            if q in (str(p.get("alias", "")).lower(), str(p.get("id", "")).lower(), str(p.get("ip", "")).lower())
        ]
        if exact:
            return exact
        return [
            p
            for p in peers
            if q in str(p.get("alias", "")).lower()
            or q in str(p.get("id", "")).lower()
            or str(p.get("ip", "")).startswith(q)
        ]
