"""GUI 收发闭环离屏测试。"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:\\Windows\\Fonts")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from aster.config import ConfigStore
from aster.gui.dialogs import ReceiveDialog
from aster.gui.main_window import MainWindow
from aster.server import AsterNode

BASE = ROOT / "build" / "gui_e2e"
shutil.rmtree(BASE, ignore_errors=True)
BASE.mkdir(parents=True)

recv_store = ConfigStore(
    data_dir=BASE / "recv_data",
    download_dir=BASE / "recv_dl",
    port=48110,
    alias="客厅电脑",
    auto_accept=True,
)
receiver = AsterNode(recv_store, port=48110, enable_discovery=False)
receiver.start()

store = ConfigStore(
    data_dir=BASE / "gui_data",
    download_dir=BASE / "dl",
    port=48100,
    alias="Aster 工作站",
    auto_accept=False,
)
node = AsterNode(store, port=48100, enable_discovery=False)
node.start()
app = QApplication([])
win = MainWindow(node)
win.show()
QTest.qWait(300)

# 设备卡片
peer = receiver.device_info()
node.remember_peer(peer, "127.0.0.1", receiver.port)
win._refresh()
QTest.qWait(200)
print("device cards", list(win.device_cards))
win.select_target("peer", node.list_peers()[0])
src = BASE / "gui-send.txt"
src.write_text("GUI 发送测试\n" * 1000, encoding="utf-8")
win._add_paths([str(src)])
QTest.qWait(200)
win.grab().save(str(BASE / "gui-send-selected.png"))

win.send_selected()
for _ in range(80):
    QTest.qWait(100)
    if not win.send_busy:
        break
QTest.qWait(300)
win.grab().save(str(BASE / "gui-sent.png"))
target = BASE / "recv_dl" / src.name
print("send result", target.exists(), target.stat().st_size if target.exists() else 0)

# 接收确认：receiver 向 GUI 发文件，GUI 弹出确认框后自动接受
incoming = BASE / "incoming.txt"
incoming.write_text("GUI 接收测试\n" * 500, encoding="utf-8")
result_holder = {}

def send_incoming() -> None:
    result_holder["result"] = receiver.send_to_peer(node.device_info(), [str(incoming)])

thread = threading.Thread(target=send_incoming, daemon=True)
thread.start()

accepted = {"ok": False}

def accept_dialog() -> None:
    for widget in app.topLevelWidgets():
        if isinstance(widget, ReceiveDialog) and widget.isVisible():
            widget.accept()
            accepted["ok"] = True
            return
    QTimer.singleShot(250, accept_dialog)

QTimer.singleShot(300, accept_dialog)
for _ in range(120):
    QTest.qWait(100)
    win._refresh()
    if not thread.is_alive() and result_holder:
        break
QTest.qWait(300)
win.grab().save(str(BASE / "gui-receive.png"))
print("dialog accepted", accepted["ok"])
print("incoming result", result_holder.get("result", {}).get("status"))
received = BASE / "dl" / incoming.name
print("receive file", received.exists(), received.stat().st_size if received.exists() else 0)

win._quitting = True
win.close()
node.stop()
receiver.stop()
print("GUI E2E DONE")
