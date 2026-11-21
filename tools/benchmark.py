"""Aster 大文件测速：HTTP vs HTTPS，本机 loopback。

用法：
  python tools/benchmark.py --sizes 1,4 --modes http,https
  python tools/benchmark.py --sizes 1 --modes http --keep

结果输出到 build/benchmark/result.json，并打印表格。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aster.config import ConfigStore
from aster.server import AsterNode

BASE = ROOT / "build" / "benchmark"
HTTP_BASE = 48020
HTTPS_BASE = 48030
CHUNK = 8 * 1024 * 1024


@dataclass
class Result:
    mode: str
    size_mib: int
    seconds: float
    mib_per_second: float
    status: str
    error: str
    file_count: int
    total_bytes: int
    sha_ok: bool
    sender_cpu_seconds: float | None = None


def make_file(path: Path, size_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pattern = b"Aster-2.0-benchmark-"
    block = (pattern * (CHUNK // len(pattern) + 1))[:CHUNK]
    remaining = size_bytes
    with open(path, "wb") as fh:
        while remaining > 0:
            take = min(CHUNK, remaining)
            fh.write(block[:take])
            remaining -= take


def run_one(mode: str, size_gib: float, *, keep: bool) -> Result:
    size_bytes = int(size_gib * 1024 * 1024 * 1024)
    label = f"{mode}_{size_gib:g}g"
    work = BASE / label
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    recv_port = HTTPS_BASE if mode == "https" else HTTP_BASE
    send_port = recv_port + 100
    recv_store = ConfigStore(
        data_dir=work / "recv_data",
        download_dir=work / "recv_dl",
        port=recv_port,
        alias="测速接收端",
        auto_accept=True,
    )
    recv = AsterNode(recv_store, port=recv_port, enable_discovery=False)
    recv.start()
    send_store = ConfigStore(
        data_dir=work / "send_data",
        download_dir=work / "send_dl",
        port=send_port,
        alias="测速发送端",
    )
    send = AsterNode(send_store, port=send_port, enable_discovery=False)
    send.start()
    if mode == "https":
        send.set_prefer_https(True)

    src = work / f"benchmark-{size_gib:g}G.bin"
    print(f"[{label}] 生成 {size_gib:g} GiB 源文件…", flush=True)
    make_file(src, size_bytes)
    peer = recv.device_info()
    print(
        f"[{label}] 发送：{send.pair_url()} -> {peer.get('web_url')} "
        f"（TLS={send.config.prefer_https and bool(recv.tls_material)}）",
        flush=True,
    )
    cpu0 = time.process_time()
    started = time.perf_counter()
    result = send.send_to_peer(peer, [str(src)])
    elapsed = max(0.0001, time.perf_counter() - started)
    cpu = max(0.0, time.process_time() - cpu0)
    target = work / "recv_dl" / src.name
    sha_ok = False
    if target.exists() and target.stat().st_size == src.stat().st_size:
        import hashlib

        def digest(path: Path) -> str:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                while True:
                    b = fh.read(8 * 1024 * 1024)
                    if not b:
                        break
                    h.update(b)
            return h.hexdigest()

        sha_ok = digest(src) == digest(target)
    mib = size_bytes / (1024 * 1024)
    out = Result(
        mode=mode,
        size_mib=int(mib),
        seconds=round(elapsed, 3),
        mib_per_second=round(mib / elapsed, 2),
        status=str(result.get("status")),
        error=str(result.get("error") or ""),
        file_count=len(result.get("files") or []),
        total_bytes=int(result.get("total_bytes") or 0),
        sha_ok=sha_ok,
        sender_cpu_seconds=round(cpu, 3),
    )
    print(
        f"[{label}] {out.status}  {out.mib_per_second:.1f} MiB/s  "
        f"{out.seconds:.2f}s  sha={sha_ok}  {out.error}",
        flush=True,
    )
    send.stop()
    recv.stop()
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Aster HTTP/HTTPS 大文件 loopback 测速")
    parser.add_argument("--sizes", default="1,4", help="逗号分隔，单位 GiB")
    parser.add_argument("--modes", default="http,https", help="http,https 组合")
    parser.add_argument("--keep", action="store_true", help="保留测试文件")
    args = parser.parse_args()
    sizes = [float(x) for x in args.sizes.split(",") if x.strip()]
    modes = [x.strip().lower() for x in args.modes.split(",") if x.strip()]
    BASE.mkdir(parents=True, exist_ok=True)
    results: list[Result] = []
    for mode in modes:
        if mode not in ("http", "https"):
            raise SystemExit(f"未知模式：{mode}")
        for size in sizes:
            results.append(run_one(mode, size, keep=args.keep))
    out = BASE / "result.json"
    out.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n| 模式 | 大小 | 耗时 | 吞吐 | 状态 | SHA |")
    print("|---|---:|---:|---:|---|---|")
    for r in results:
        print(
            f"| {r.mode.upper()} | {r.size_mib / 1024:g} GiB | {r.seconds:.2f}s | "
            f"{r.mib_per_second:.1f} MiB/s | {r.status} | {'✓' if r.sha_ok else '✗'} |"
        )
    print(f"\n结果：{out}")
    return 0 if all(r.status == "completed" and r.sha_ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
