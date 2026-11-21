"""HTTPS 双端口与加密对等传输冒烟测试。"""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aster.config import ConfigStore
from aster.server import AsterNode

BASE = ROOT / "build" / "https_test"
shutil.rmtree(BASE, ignore_errors=True)
BASE.mkdir(parents=True)
ctx = ssl._create_unverified_context()

recv_store = ConfigStore(
    data_dir=BASE / "recv_data", download_dir=BASE / "recv_dl",
    port=47902, alias="HTTPS接收端", auto_accept=True,
)
recv = AsterNode(recv_store, port=47902, enable_discovery=False)
recv.start()
print("recv ports", recv.port, recv.https_port, "tls", bool(recv.tls_material), recv.tls_error)

for url in (f"http://127.0.0.1:{recv.port}/api/v1/ping", f"https://127.0.0.1:{recv.https_port}/api/v1/ping"):
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=10) as r:
            print(url, r.status, r.read(120))
    except Exception as e:
        print(url, "ERR", e)
for url in (f"https://127.0.0.1:{recv.https_port}/", f"https://127.0.0.1:{recv.https_port}/app.js"):
    with urllib.request.urlopen(url, context=ctx, timeout=10) as r:
        print(url, r.status, len(r.read()))

pair = recv.pair_web(recv.config.web_pair_code, "HTTPS手机", "test", "127.0.0.1")
print("pair https", bool(pair["token"]))
with urllib.request.urlopen(
    urllib.request.Request(f"https://127.0.0.1:{recv.https_port}/api/v1/web/state",
                           headers={"X-Aster-Web-Token": pair["token"]}),
    context=ctx, timeout=10,
) as r:
    st = json.loads(r.read())
    print("https state", st["device"]["alias"], st["https_url"])

# 发送端开启 prefer_https，向接收端发送
send_store = ConfigStore(data_dir=BASE / "send_data", download_dir=BASE / "send_dl",
                         port=47900, alias="HTTPS发送端")
send = AsterNode(send_store, port=47900, enable_discovery=False)
send.start()
send.set_prefer_https(True)
print("sender prefer", send.config.prefer_https, send.pair_url())
src = BASE / "encrypted.txt"
src.write_text("HTTPS 加密传输测试\n" * 1000, encoding="utf-8")
peer = recv.device_info()
print("peer https", peer.get("https_port"), peer.get("tls_fingerprint"))
result = send.send_to_peer(peer, [str(src)])
print("send result", result.get("status"), result.get("error"), result.get("total_bytes"))
target = BASE / "recv_dl" / src.name
print("target", target.exists(), target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(src.read_bytes()).hexdigest())

send.stop()
recv.stop()
print("HTTPS OK")
