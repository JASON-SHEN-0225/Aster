"""GUI 离屏渲染冒烟测试。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:\\Windows\\Fonts")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from aster.config import ConfigStore
from aster.gui.main_window import MainWindow
from aster.server import AsterNode

BASE = ROOT / "build" / "gui_smoke"
shutil.rmtree(BASE, ignore_errors=True)
BASE.mkdir(parents=True)
store = ConfigStore(
    data_dir=BASE / "data",
    download_dir=BASE / "dl",
    port=48100,
    alias="Aster 工作站",
    auto_accept=True,
)
node = AsterNode(store, port=48100, enable_discovery=False)
node.start()
app = QApplication([])
win = MainWindow(node)
win.show()
app.processEvents()
for i in range(8):
    app.processEvents()
    win._refresh()
    app.processEvents()

shots = ROOT / "build" / "gui-shots"
shots.mkdir(parents=True, exist_ok=True)
win.grab().save(str(shots / "01-send-light.png"))
win.show_page(1)
QTest.qWait(260)
win.grab().save(str(shots / "02-transfers-light.png"))
win.show_page(2)
QTest.qWait(260)
win.grab().save(str(shots / "03-history-light.png"))
win.show_page(3)
QTest.qWait(260)
win.grab().save(str(shots / "04-settings-light.png"))
win.apply_theme("dark")
QTest.qWait(150)
win.show_page(0)
QTest.qWait(260)
win.grab().save(str(shots / "05-send-dark.png"))
print("shots", list(shots.glob("*.png")))
print("size", win.size().width(), win.size().height())
win._quitting = True
win.close()
node.stop()
print("GUI SMOKE OK")
