"""资源管理器右键与 GUI 共用的小型预传输队列。

每个入队请求写一个独立 JSON 文件，GUI 轮询后消费并删除，避免两个进程
同时改写同一个队列文件。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Iterable


class QueueStore:
    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.queue_dir = self.data_dir / "inbox"

    def enqueue(self, paths: Iterable[str]) -> int:
        clean: list[str] = []
        seen: set[str] = set()
        for raw in paths:
            if not raw:
                continue
            try:
                path = str(Path(raw).expanduser().resolve())
            except OSError:
                path = str(Path(raw).expanduser().absolute())
            if path and path not in seen:
                seen.add(path)
                clean.append(path)
        if not clean:
            return 0
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "id": uuid.uuid4().hex,
            "created": time.time(),
            "paths": clean,
        }
        target = self.queue_dir / f"{entry['created']:.6f}-{entry['id']}.json"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        return len(clean)

    def drain(self) -> list[str]:
        if not self.queue_dir.is_dir():
            return []
        paths: list[str] = []
        seen: set[str] = set()
        for entry in sorted(self.queue_dir.glob("*.json")):
            try:
                data = json.loads(entry.read_text(encoding="utf-8"))
                items = data.get("paths") if isinstance(data, dict) else None
                for raw in items or []:
                    if isinstance(raw, str) and raw and raw not in seen:
                        seen.add(raw)
                        paths.append(raw)
            except (OSError, ValueError, TypeError):
                pass
            finally:
                try:
                    entry.unlink()
                except OSError:
                    pass
        return paths
