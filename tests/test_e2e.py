"""Aster 端到端测试（不依赖 pytest）。"""

from __future__ import annotations

import hashlib
import http.client
import json
import shutil
import socket
import ssl
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from aster.client import PeerClient, PeerError
from aster.config import ConfigStore
from aster.server import AsterNode

BASE = Path(__file__).resolve().parent.parent / "build" / "tests"
BASE.mkdir(parents=True, exist_ok=True)


def sender_device() -> dict:
    return {
        "id": uuid.uuid4().hex,
        "alias": "测试发送端",
        "device_type": "desktop",
        "version": "1.0.0",
        "protocol": 1,
        "platform": "Windows 11",
        "fingerprint": "0123456789abcdef",
        "port": 47999,
    }


class AsterE2E(unittest.TestCase):
    port_counter = 47910

    def setUp(self) -> None:
        self.name = self._testMethodName
        type(self).port_counter += 1
        self.port = type(self).port_counter
        self.dir = BASE / self.name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.store = ConfigStore(
            data_dir=self.dir / "data",
            download_dir=self.dir / "downloads",
            port=self.port,
            alias="测试接收端",
            auto_accept=True,
        )
        self.node = AsterNode(
            self.store, port=self.port, enable_discovery=False
        )
        self.node.start()
        self.client = PeerClient("127.0.0.1", self.port)

    def tearDown(self) -> None:
        self.node.stop()
        time.sleep(0.05)

    # -- helpers -----------------------------------------------------
    def make_file(self, name: str, content: bytes) -> Path:
        path = self.dir / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def files_payload(self, path: Path, rel_path: str | None = None) -> dict:
        return {
            "id": uuid.uuid4().hex,
            "name": path.name,
            "rel_path": rel_path or path.name,
            "size": path.stat().st_size,
        }

    def request(self, files: list[dict], text: str = "", pin: str = "") -> dict:
        return self.client.request_transfer(
            sender_device(), files, text=text, pin=pin, timeout=15
        )

    def send_one(self, path: Path, rel_path: str | None = None) -> dict:
        payload = self.files_payload(path, rel_path)
        resp = self.request([payload])
        token = resp["tokens"][payload["id"]]
        _, sha = self.client.upload_file(
            resp["session_id"], payload["id"], token, path
        )
        if sha is None:
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.client.complete_file(resp["session_id"], payload["id"], token, sha)
        return resp

    def pair_web(self, name: str = "测试手机") -> dict:
        console = self.node.pair_web(
            self.node.config.web_pair_code, name, "Android Chrome", "127.0.0.1"
        )
        return console

    def web_req(self, path: str, data=None, token: str = "", raw: bytes | None = None):
        headers = {}
        if data is not None:
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Aster-Web-Token"] = token
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=raw,
            headers=headers,
            method="POST" if raw is not None else "GET",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read()

    # -- tests -------------------------------------------------------
    def test_file_text_roundtrip(self) -> None:
        content = "你好，星流！\n".encode("utf-8") + b"x" * 5000
        path = self.make_file("hello 世界.txt", content)
        resp = self.request([self.files_payload(path, "文档/hello 世界.txt")], text="剪贴板文本")
        self.assertTrue(resp["accepted"])
        token = resp["tokens"][next(iter(resp["tokens"]))]
        data, sha = self.client.upload_file(
            resp["session_id"], next(iter(resp["tokens"])), token, path
        )
        self.assertTrue(data["complete"])
        self.client.complete_file(
            resp["session_id"], next(iter(resp["tokens"])), token, sha or ""
        )
        target = self.dir / "downloads" / "文档" / "hello 世界.txt"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(self.node.texts[-1]["text"], "剪贴板文本")
        history = self.node.history.list(5)
        self.assertEqual(history[0]["status"], "completed")
        time.sleep(0.05)
        completed = [
            item
            for item in self.node.snapshot()["transfers"]
            if item["status"] == "completed" and item["kind"] == "files"
        ]
        self.assertTrue(completed)
        self.assertGreater(completed[0]["avg_speed"], 0)
        self.assertGreater(completed[0]["speed"], 0)
        self.assertEqual(history[0]["direction"], "in")

    def test_folder_dedup_and_empty(self) -> None:
        path = self.make_file("a.txt", b"same")
        self.send_one(path, "项目/sub/a.txt")
        self.send_one(path, "项目/sub/a.txt")
        target1 = self.dir / "downloads" / "项目" / "sub" / "a.txt"
        target2 = self.dir / "downloads" / "项目" / "sub" / "a (1).txt"
        self.assertTrue(target1.exists())
        self.assertTrue(target2.exists())
        self.assertEqual(target1.read_bytes(), b"same")
        # 零字节文件
        empty = self.make_file("empty.bin", b"")
        self.send_one(empty, "项目/empty.bin")
        self.assertTrue((self.dir / "downloads" / "项目" / "empty.bin").exists())

    def test_resume_from_offset(self) -> None:
        content = bytes(range(256)) * 4000  # 1 MiB
        path = self.make_file("resume.bin", content)
        payload = self.files_payload(path)
        resp = self.request([payload])
        sid = resp["session_id"]
        fid = payload["id"]
        token = resp["tokens"][fid]
        half = len(content) // 2
        q = urllib.parse.urlencode(
            {"session_id": sid, "file_id": fid, "token": token, "offset": 0}
        )
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        conn.request(
            "POST",
            f"/api/v1/transfer/upload?{q}",
            body=content[:half],
            headers={"Content-Type": "application/octet-stream"},
        )
        r = conn.getresponse()
        data = json.loads(r.read().decode())
        conn.close()
        self.assertEqual(data["received"], half)
        status = self.client.get_status(sid, fid, token)
        self.assertEqual(status["received"], half)
        _, sha = self.client.upload_file(sid, fid, token, path, offset=half)
        full_sha = hashlib.sha256(content).hexdigest()
        self.client.complete_file(sid, fid, token, full_sha)
        target = self.dir / "downloads" / "resume.bin"
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(full_sha, hashlib.sha256(target.read_bytes()).hexdigest())

    def test_reject_then_pin(self) -> None:
        self.node.config.auto_accept = False
        path = self.make_file("reject.txt", b"no")
        payload = self.files_payload(path)
        result: dict = {}

        def work() -> None:
            try:
                self.client.request_transfer(sender_device(), [payload], timeout=20)
                result["ok"] = True
            except PeerError as exc:
                result["error"] = exc

        th = threading.Thread(target=work, daemon=True)
        th.start()
        pending = []
        for _ in range(50):
            pending = self.node.list_pending()
            if pending:
                break
            time.sleep(0.05)
        self.assertTrue(pending)
        self.node.decide_pending(pending[0]["id"], False)
        th.join(timeout=5)
        self.assertIn("error", result)
        self.assertEqual(result["error"].status, 403)

        # PIN 错
        self.node.config.pin = "1234"
        with self.assertRaises(PeerError) as ctx:
            self.request([], text="pin test", pin="0000")
        self.assertEqual(ctx.exception.status, 403)
        # PIN 对（自动接受仍未开，走手动接受）
        result2: dict = {}

        def work2() -> None:
            try:
                result2["resp"] = self.client.request_transfer(
                    sender_device(), [], text="pin ok", pin="1234", timeout=20
                )
            except PeerError as exc:
                result2["error"] = exc

        th2 = threading.Thread(target=work2, daemon=True)
        th2.start()
        pending2 = []
        for _ in range(50):
            pending2 = self.node.list_pending()
            if pending2:
                break
            time.sleep(0.05)
        self.assertTrue(pending2)
        self.node.decide_pending(pending2[0]["id"], True)
        th2.join(timeout=5)
        self.assertIn("resp", result2)
        self.assertEqual(self.node.texts[-1]["text"], "pin ok")

    def test_web_pair_upload_and_offer_download(self) -> None:
        # 错误配对码
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.web_req("/api/v1/web/pair", {"code": "000000", "name": "x"})
        self.assertEqual(ctx.exception.code, 403)
        pair = self.pair_web()
        token = pair["token"]
        state = json.loads(self.web_req("/api/v1/web/state", token=token)[1])
        self.assertTrue(state["web"]["paired"])

        # 手机上传到电脑
        src = self.make_file("phone.txt", "来自手机 中文".encode("utf-8"))
        fid = uuid.uuid4().hex
        status, body = self.web_req(
            "/api/v1/web/request",
            {
                "files": [
                    {
                        "id": fid,
                        "name": src.name,
                        "rel_path": "手机/phone.txt",
                        "size": src.stat().st_size,
                    }
                ]
            },
            token=token,
        )
        sess = json.loads(body)
        ftoken = sess["tokens"][fid]
        q = urllib.parse.urlencode(
            {"session_id": sess["session_id"], "file_id": fid, "token": ftoken, "offset": 0}
        )
        status, body = self.web_req(
            f"/api/v1/transfer/upload?{q}", raw=src.read_bytes(), token=token
        )
        self.assertEqual(status, 200)
        status, body = self.web_req(
            "/api/v1/transfer/complete",
            {
                "session_id": sess["session_id"],
                "file_id": fid,
                "token": ftoken,
                "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
            },
            token=token,
        )
        self.assertEqual(status, 200)
        self.assertTrue((self.dir / "downloads" / "手机" / "phone.txt").exists())

        # 电脑 → 手机 offer + Range 下载
        offer_src = self.make_file("pc-offer.txt", "电脑发到手机".encode("utf-8"))
        out = self.node.send_to_web(str(pair["web_id"]), [str(offer_src)], text="文本也来")
        offer = out["offer"]
        oid = offer["id"]
        ofid = offer["files"][0]["id"]
        status, body = self.web_req(
            f"/api/v1/web/offers/{oid}/respond", {"accept": True}, token=token
        )
        self.assertEqual(status, 200)
        url = (
            f"http://127.0.0.1:{self.port}/api/v1/web/offers/{oid}/files/{ofid}/download"
            f"?token={urllib.parse.quote(token)}"
        )
        req = urllib.request.Request(url, headers={"Range": "bytes=0-5"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            self.assertEqual(resp.status, 206)
            self.assertEqual(resp.read(), "电脑发到手机".encode("utf-8")[:6])
        with urllib.request.urlopen(url, timeout=20) as resp:
            self.assertEqual(resp.read(), "电脑发到手机".encode("utf-8"))
        time.sleep(0.1)
        state = json.loads(self.web_req("/api/v1/web/state", token=token)[1])
        offer_now = next(o for o in state["offers"] if o["id"] == oid)
        self.assertEqual(offer_now["status"], "completed")

    def test_web_offer_cancel_download(self) -> None:
        pair = self.pair_web("取消测试手机")
        token = pair["token"]
        ws = self.node.web_sessions[pair["web_id"]]
        source = self.dir / "src" / "cancel-large.bin"
        source.parent.mkdir(parents=True, exist_ok=True)
        with source.open("wb") as fh:
            fh.truncate(256 * 1024 * 1024)
        out = self.node.send_to_web(str(pair["web_id"]), [str(source)])
        offer = out["offer"]
        oid = offer["id"]
        ofid = offer["files"][0]["id"]
        status, _ = self.web_req(
            f"/api/v1/web/offers/{oid}/respond", {"accept": True}, token=token
        )
        self.assertEqual(status, 200)
        url = (
            f"/api/v1/web/offers/{oid}/files/{ofid}/download"
            f"?token={urllib.parse.quote(token)}"
        )
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request("GET", url)
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(len(resp.read(4096)), 4096)
        cancel_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/v1/web/offers/{oid}/cancel",
            data=b"",
            headers={"X-Aster-Web-Token": token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(cancel_req, timeout=10) as cancel_resp:
            self.assertEqual(json.loads(cancel_resp.read())["status"], "cancelled")
        time.sleep(0.2)
        try:
            resp.read(1)
        except (OSError, http.client.HTTPException):
            pass
        conn.close()
        self.assertEqual(self.node.transfers[out["transfer"]["id"]]["status"], "cancelled")
        self.assertEqual(self.node.offers[oid].status, "cancelled")
        with self.assertRaises(Exception):
            self.node.serve_offer_download(
                type("H", (), {"connection": None}), ws, oid, ofid
            )

    def test_discovery_announce(self) -> None:
        self.node.discovery = None
        self.node.stop()
        self.node = AsterNode(self.store, port=self.port, enable_discovery=True)
        self.node.start()
        peer_id = uuid.uuid4().hex
        msg = {
            "app": "aster",
            "protocol": 1,
            "type": "announce",
            "device": {
                "id": peer_id,
                "alias": "隔壁电脑",
                "device_type": "desktop",
                "version": "1.0.0",
                "port": 47820,
                "fingerprint": "abcdefabcdefabcd",
            },
        }
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(json.dumps(msg).encode(), ("127.0.0.1", self.port))
        sock.close()
        found = None
        for _ in range(30):
            found = next((p for p in self.node.list_peers() if p.get("id") == peer_id), None)
            if found:
                break
            time.sleep(0.05)
        self.assertIsNotNone(found)
        self.assertEqual(found["alias"], "隔壁电脑")
        self.assertEqual(found["ip"], "127.0.0.1")

    def test_peer_hello_and_history(self) -> None:
        device = sender_device()
        resp = self.client.hello(device)
        self.assertTrue(resp["ok"])
        self.assertTrue(any(p["id"] == device["id"] for p in self.node.list_peers()))
        # 文本历史
        result = self.request([], text="历史文本")
        self.assertTrue(result["accepted"])
        time.sleep(0.05)
        items = self.node.public_history(10)
        self.assertTrue(any(item.get("text") == "历史文本" for item in items))

    def test_text_only_auto_complete(self) -> None:
        result = self.request([], text="只有文本")
        self.assertTrue(result["accepted"])
        time.sleep(0.05)
        items = self.node.snapshot()["transfers"]
        self.assertTrue(any(t["status"] == "completed" and t["kind"] == "text" for t in items))

    def test_https_web_and_peer_transfer(self) -> None:
        ctx = ssl._create_unverified_context()
        https_base = f"https://127.0.0.1:{self.node.https_port}"
        with urllib.request.urlopen(f"{https_base}/api/v1/ping", context=ctx, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(json.loads(resp.read())["app"], "Aster")
        with urllib.request.urlopen(f"{https_base}/app.js", context=ctx, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            self.assertGreater(len(resp.read()), 1000)

        pair = self.node.pair_web(self.node.config.web_pair_code, "HTTPS 手机", "Android", "127.0.0.1")
        token = pair["token"]
        req = urllib.request.Request(
            f"{https_base}/api/v1/web/settings",
            data=json.dumps({"prefer_https": True}).encode("utf-8"),
            headers={"X-Aster-Web-Token": token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            body = json.loads(resp.read())
        self.assertTrue(body["settings"]["prefer_https"])
        self.assertTrue(self.node.config.prefer_https)
        self.assertTrue(self.node.pair_url().startswith("https://"))

        # 另起一个优先 HTTPS 的发送端，向本接收端发送文件
        send_store = ConfigStore(
            data_dir=self.dir / "https_send_data",
            download_dir=self.dir / "https_send_dl",
            port=self.port + 20,
            alias="HTTPS 发送端",
        )
        send_node = AsterNode(send_store, port=self.port + 20, enable_discovery=False)
        send_node.start()
        try:
            send_node.set_prefer_https(True)
            src = self.make_file("https-peer.txt", b"encrypted peer payload")
            result = send_node.send_to_peer(self.node.device_info(), [str(src)])
            self.assertEqual(result["status"], "completed", result.get("error"))
            target = self.dir / "downloads" / src.name
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), src.read_bytes())
        finally:
            send_node.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
