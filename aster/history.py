"""传输历史（本地 JSON，线程安全）。"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .util import atomic_write_json, read_json


class HistoryStore:
    def __init__(self, path: Path, limit: int = 300):
        self.path = Path(path)
        self.limit = limit
        self._lock = threading.RLock()
        self._items: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        raw = read_json(self.path, [])
        if isinstance(raw, list):
            self._items = [x for x in raw if isinstance(x, dict)][-self.limit :]
        else:
            self._items = []

    def _flush(self) -> None:
        atomic_write_json(self.path, self._items[-self.limit :])

    @staticmethod
    def new_entry(
        *,
        kind: str,
        direction: str,
        peer: dict[str, Any] | None = None,
        files: list[dict[str, Any]] | None = None,
        text: str = "",
        via: str = "peer",
        status: str = "pending",
    ) -> dict[str, Any]:
        now = time.time()
        return {
            "id": uuid.uuid4().hex,
            "kind": kind,  # send / receive / text_send / text_receive
            "direction": direction,  # out / in
            "peer": peer or {},
            "files": files or [],
            "text": text,
            "via": via,
            "status": status,
            "started_at": now,
            "finished_at": None,
            "total_bytes": sum(int(f.get("size") or 0) for f in (files or [])),
            "error": "",
        }

    def add(self, entry: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._items.append(copy.deepcopy(entry))
            self._items = self._items[-self.limit :]
            self._flush()
            return copy.deepcopy(entry)

    def update(self, entry_id: str, **fields: Any) -> Optional[dict[str, Any]]:
        with self._lock:
            for item in reversed(self._items):
                if item.get("id") == entry_id:
                    item.update(fields)
                    if fields.get("status") in ("completed", "failed", "cancelled", "rejected"):
                        item.setdefault("finished_at", time.time())
                    self._flush()
                    return copy.deepcopy(item)
            return None

    def get(self, entry_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            for item in reversed(self._items):
                if item.get("id") == entry_id:
                    return copy.deepcopy(item)
            return None

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._items[-limit:][::-1])

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._flush()
