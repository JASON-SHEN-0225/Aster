"""电脑 → 手机 offer 的真实浏览器测试编排。"""

from __future__ import annotations
import os

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aster.config import ConfigStore
from aster.server import AsterNode

BASE = ROOT / "build" / "offer_e2e"
shutil.rmtree(BASE, ignore_errors=True)
BASE.mkdir(parents=True, exist_ok=True)
WEBID_FILE = ROOT / "build" / "offer_webid.txt"
WEBID_FILE.unlink(missing_ok=True)

store = ConfigStore(
    data_dir=BASE / "data",
    download_dir=BASE / "dl",
    port=47883,
    alias="Offer 测试电脑",
    auto_accept=True,
)
node = AsterNode(store, port=47883, enable_discovery=False)
node.start()
url = f"http://127.0.0.1:47883"
code = node.config.web_pair_code
print("server", url, "code", code)

source = BASE / "电脑发来的文件.txt"
size = int(os.environ.get("OFFER_BYTES", "630"))
payload = ("来自电脑的 offer 内容\n" + "星流" * 100).encode("utf-8")
source.write_bytes((payload * ((size // len(payload)) + 1))[:size])

proc = subprocess.Popen(
    ["node", str(ROOT / "tools" / "uiprobe" / "offer_probe.js"), url, code],
    cwd=str(ROOT),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
)

web_id = None
deadline = time.time() + 30
while time.time() < deadline:
    if WEBID_FILE.exists():
        text = WEBID_FILE.read_text(encoding="utf-8").strip()
        if text:
            web_id = text
            break
    if proc.poll() is not None:
        break
    time.sleep(0.2)
if not web_id:
    proc.kill()
    print("NO WEB ID", proc.communicate()[0])
    node.stop()
    raise SystemExit(1)

print("web_id", web_id)
time.sleep(0.5)
out = node.send_to_web(web_id, [str(source)], text="电脑发来的说明文本")
offer = out["offer"]
print("offer", json.dumps(offer, ensure_ascii=False)[:500])
try:
    stdout, _ = proc.communicate(timeout=90)
except subprocess.TimeoutExpired:
    proc.kill()
    stdout, _ = proc.communicate()
print("--- browser ---")
print(stdout)

try:
    browser_result = json.loads(stdout[stdout.find("{") :]) if "{" in stdout else {}
except ValueError:
    browser_result = {}

expected_sha = hashlib.sha256(source.read_bytes()).hexdigest()
print("expected sha", expected_sha)
print("browser sha", browser_result.get("downloadSha"))
print("browser fatal", browser_result.get("fatal"))

# 等 offer 完成
for _ in range(30):
    offer_now = node.offers.get(offer["id"])
    if offer_now and offer_now.status == "completed":
        break
    time.sleep(0.2)
offer_now = node.offers.get(offer["id"])
print("final offer status", offer_now.status if offer_now else None)
print("history", json.dumps(node.history.list(3), ensure_ascii=False)[:800])
node.stop()

ok = (
    browser_result.get("downloadSha") == expected_sha
    and not browser_result.get("errors")
    and browser_result.get("accepted")
)
print("OFFER E2E", "OK" if ok else "FAILED")
raise SystemExit(0 if ok else 1)
