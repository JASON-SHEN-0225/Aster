"""GUI 入口。"""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_CN, APP_NAME, DEFAULT_PORT, VERSION
from ..config import ConfigStore
from ..queue import QueueStore
from ..server import AsterNode
from ..shellmenu import register as register_shell_menu
from ..single_instance import SingleInstance
from .icons import app_icon
from .main_window import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="Aster", description=f"{APP_NAME} · {APP_CN} 图形界面")
    parser.add_argument("--port", type=int, default=None, help=f"HTTP 端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--name", default=None, help="设备名称")
    parser.add_argument("--dir", default=None, help="接收目录")
    parser.add_argument("--data-dir", default=None, help="配置/历史目录")
    parser.add_argument("--auto-accept", action="store_true", help="自动接受传输")
    parser.add_argument("--prefer-https", action="store_true", help="优先使用 HTTPS")
    parser.add_argument("--no-discovery", action="store_true", help="关闭 UDP 发现")
    parser.add_argument("--minimized", action="store_true", help="启动后最小化到托盘")
    parser.add_argument(
        "--enqueue",
        nargs="+",
        default=None,
        metavar="PATH",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    return parser


def run_gui(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.enqueue:
        try:
            store = ConfigStore(
                data_dir=Path(args.data_dir) if args.data_dir else None,
                port=args.port,
                alias=args.name,
                download_dir=args.dir,
            )
            QueueStore(store.data_dir).enqueue(args.enqueue)
        except Exception:
            return 1
        probe = SingleInstance()
        running = probe.already_running
        probe.release()
        if running:
            return 0

    guard = SingleInstance()
    if guard.already_running:
        guard.release()
        if not args.enqueue:
            try:
                ctypes.windll.user32.MessageBoxW(None, "Aster 已在运行", APP_NAME, 0x40)
            except Exception:
                pass
        return 0

    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(f"{APP_NAME} · {APP_CN}")
    app.setOrganizationName("Aster")
    app.setWindowIcon(app_icon())
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    font = QFont()
    font.setFamily("Segoe UI Variable")
    font.setPointSize(10)
    app.setFont(font)

    try:
        register_shell_menu()
    except Exception:
        pass

    store = ConfigStore(
        data_dir=Path(args.data_dir) if args.data_dir else None,
        port=args.port,
        alias=args.name,
        download_dir=args.dir,
        auto_accept=True if args.auto_accept else None,
        prefer_https=True if args.prefer_https else None,
    )
    node = AsterNode(
        store,
        port=args.port or store.config.port,
        enable_discovery=not args.no_discovery,
    )
    try:
        node.start()
    except Exception as exc:
        QMessageBox.critical(None, "Aster 无法启动", str(exc))
        guard.release()
        return 2
    window = MainWindow(node, minimized=args.minimized)
    if not args.minimized:
        window.show()
    app.aboutToQuit.connect(node.stop)
    try:
        return app.exec()
    finally:
        guard.release()


if __name__ == "__main__":
    raise SystemExit(run_gui())
