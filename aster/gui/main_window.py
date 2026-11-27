"""Aster 主窗口：发送 / 传输 / 历史 / 设置。"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QPropertyAnimation, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_CN, APP_NAME, VERSION
from ..client import PeerClient, PeerError, expand_paths
from ..queue import QueueStore
from ..server import AsterNode
from ..shellmenu import register as register_shell_menu
from ..util import (
    format_time,
    get_clipboard_text,
    human_size,
    set_clipboard_text,
    short_time,
)
from .dialogs import InputDialog, QRDialog, ReceiveDialog, TextDialog
from .icons import app_icon, make_icon
from .theme import build_qss, palette
from .widgets import (
    DeviceCard,
    DropZone,
    EmptyHint,
    FileRow,
    GradientTitle,
    HeroLogo,
    SchemeSwitch,
    ThemeSwitch,
    Toast,
    TransferCard,
)

PAGE_SEND = 0
PAGE_TRANSFERS = 1
PAGE_HISTORY = 2
PAGE_SETTINGS = 3

STATUS_TEXT = {
    "waiting": "等待确认",
    "pending": "待接收",
    "active": "传输中",
    "uploading": "上传中",
    "verifying": "校验中",
    "finalizing": "写入中",
    "completed": "已完成",
    "failed": "失败",
    "rejected": "已拒绝",
    "cancelled": "已取消",
}


class MainWindow(QMainWindow):
    update_checked = Signal(dict)

    def __init__(self, node: AsterNode, *, minimized: bool = False):
        super().__init__()
        self.node = node
        self.config = node.config
        self.inbox = QueueStore(node.store.data_dir)
        self.theme = self.config.theme if self.config.theme in ("light", "dark") else "light"
        self.selected_paths: list[str] = []
        self.selection_files: list[dict[str, Any]] = []
        self.target: Optional[dict[str, Any]] = None
        self.target_kind: str = ""
        self.device_cards: dict[str, DeviceCard] = {}
        self.device_signature: Any = None
        self.transfer_cards: dict[str, TransferCard] = {}
        self.transfer_signature: tuple[Any, ...] = ()
        self.history_counter = 0
        self.send_busy = False
        self.send_thread: Optional[threading.Thread] = None
        self.send_result: Optional[dict[str, Any]] = None
        self.send_summary = ""
        self._pending_open = False
        self._quitting = False
        self._first_close = True
        self._toast: Optional[Toast] = None
        self._notified_transfers: set[str] = set()
        self._minimized = minimized
        self._loading_settings = False
        self._update_busy = False
        self._update_url = ""
        self._update_checked = False

        self.setWindowTitle(f"{APP_NAME} · {APP_CN}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1040, 700)
        self.resize(1160, 780)
        QApplication.instance().setStyleSheet(build_qss(self.theme))
        self._build_ui()
        self._build_tray()
        self._apply_icons()
        self._refresh()
        self._start_timers()
        self.update_checked.connect(self._apply_update_result)
        QTimer.singleShot(120, self._after_show)
        QTimer.singleShot(1800, lambda: self.check_updates(manual=False))

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(232)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 16)
        side.setSpacing(7)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setFixedSize(38, 38)
        logo.setPixmap(make_icon("star", palette(self.theme)["accent"], 30).pixmap(30, 30))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(f"background:{palette(self.theme)['accent_soft']}; border-radius:11px;")
        self.brand_logo = logo
        words = QVBoxLayout()
        words.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("BrandName")
        cn = QLabel("星流")
        cn.setObjectName("BrandSub")
        words.addWidget(name)
        words.addWidget(cn)
        brand.addWidget(logo)
        brand.addLayout(words, 1)
        side.addLayout(brand)
        side.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_items = [
            ("发送", "upload", PAGE_SEND),
            ("传输", "refresh", PAGE_TRANSFERS),
            ("历史", "history", PAGE_HISTORY),
            ("设置", "settings", PAGE_SETTINGS),
        ]
        self.nav_buttons: list[QPushButton] = []
        for label, icon_id, page in nav_items:
            btn = QPushButton("  " + label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.setProperty("iconId", icon_id)
            btn.setProperty("pageIndex", page)
            btn.clicked.connect(lambda _=False, p=page: self.show_page(p))
            self.nav_group.addButton(btn, page)
            self.nav_buttons.append(btn)
            side.addWidget(btn)
        self.nav_buttons[PAGE_SEND].setChecked(True)
        side.addStretch(1)

        phone_card = QFrame()
        phone_card.setObjectName("Card")
        phone_layout = QVBoxLayout(phone_card)
        phone_layout.setContentsMargins(12, 11, 12, 11)
        phone_layout.setSpacing(5)
        ph_title = QLabel("手机网页")
        ph_title.setObjectName("SectionTitle")
        self.web_state = QLabel("等待手机连接")
        self.web_state.setObjectName("Muted")
        self.web_state.setWordWrap(True)
        phone_layout.addWidget(ph_title)
        phone_layout.addWidget(self.web_state)
        phone_buttons = QHBoxLayout()
        phone_buttons.setSpacing(6)
        qr_btn = QPushButton("二维码")
        qr_btn.setObjectName("Soft")
        qr_btn.setFixedHeight(32)
        qr_btn.setStyleSheet("padding: 4px 10px; font-size: 11.5px;")
        qr_btn.clicked.connect(self.show_qr)
        open_btn = QPushButton("打开")
        open_btn.setObjectName("Ghost")
        open_btn.setFixedHeight(32)
        open_btn.setStyleSheet("padding: 4px 10px; font-size: 11.5px;")
        open_btn.clicked.connect(self.open_web)
        self.qr_btn = qr_btn
        self.open_btn = open_btn
        phone_buttons.addWidget(qr_btn)
        phone_buttons.addWidget(open_btn)
        phone_layout.addLayout(phone_buttons)
        side.addWidget(phone_card)
        side.addSpacing(8)

        self.local_info = QLabel()
        self.local_info.setObjectName("Small")
        self.local_info.setWordWrap(True)
        side.addWidget(self.local_info)

        outer.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 18, 26, 18)
        content_layout.setSpacing(14)

        topbar = QHBoxLayout()
        topbar.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.page_title = QLabel("发送")
        self.page_title.setObjectName("PageTitle")
        self.page_sub = QLabel("")
        self.page_sub.setObjectName("PageSub")
        self.page_sub.hide()
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addWidget(self.page_title)
        self.scheme_switch = SchemeSwitch(self.theme)
        self.scheme_switch.changed.connect(self.toggle_prefer_https)
        title_row.addWidget(self.scheme_switch)
        title_row.addStretch(1)
        titles.addLayout(title_row)
        titles.addWidget(self.page_sub)
        topbar.addLayout(titles, 1)

        self.conn_pill = QLabel("在线")
        self.conn_pill.setObjectName("Pill")
        self.conn_pill.setStyleSheet(
            "background:#E3F8F3; color:#0D9F6E; border-radius:11px; padding:4px 11px; font-size:14px; font-weight:650;"
        )
        refresh = QPushButton()
        refresh.setObjectName("Ghost")
        refresh.setFixedSize(34, 32)
        refresh.setIcon(make_icon("refresh", palette(self.theme)["text2"], 15))
        refresh.setToolTip("搜索附近设备")
        refresh.clicked.connect(self.search_devices)
        self.refresh_btn = refresh
        self.theme_switch = ThemeSwitch(self.theme)
        self.theme_switch.changed.connect(self.toggle_theme)
        topbar.addWidget(self.conn_pill)
        topbar.addWidget(refresh)
        topbar.addWidget(self.theme_switch)
        content_layout.addLayout(topbar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_send_page())
        self.stack.addWidget(self._build_transfers_page())
        self.stack.addWidget(self._build_history_page())
        self.stack.addWidget(self._build_settings_page())
        content_layout.addWidget(self.stack, 1)

        outer.addWidget(content, 1)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background:{palette(self.theme)['bg']}; color:{palette(self.theme)['text3']}; font-size:12px; }}"
        )
        self.statusBar().showMessage("就绪")
        self._set_page_titles(PAGE_SEND)

    # ------------------------------------------------------------------
    def _page_scroll(self) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(14)
        scroll.setWidget(body)
        return scroll, body, layout

    def _build_send_page(self) -> QWidget:
        scroll, body, layout = self._page_scroll()
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)
        p = palette(self.theme)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 10, 22, 10)
        hero_layout.setSpacing(12)
        self.hero_logo = HeroLogo(self.theme)
        hero_layout.addWidget(self.hero_logo)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(0)
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.addStretch(1)
        self.hero_title = GradientTitle("把文件，交给星流", self.theme)
        self.hero_meta = QLabel()
        self.hero_meta.setObjectName("Muted")
        self.hero_meta.setWordWrap(False)
        self.hero_meta.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.hero_meta.setFixedHeight(24)
        self.hero_meta.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hero_text.addWidget(self.hero_title)
        hero_text.addWidget(self.hero_meta)
        hero_text.addStretch(1)
        hero_layout.addLayout(hero_text, 1)
        layout.addWidget(hero)

        dev_head = QHBoxLayout()
        dev_label = QLabel("附近设备")
        dev_label.setObjectName("SectionTitle")
        dev_head.addWidget(dev_label)
        dev_head.addStretch(1)
        manual = QPushButton("连接 IP")
        manual.setObjectName("Ghost")
        manual.setFixedHeight(31)
        manual.setStyleSheet("padding: 4px 10px; font-size: 11.5px;")
        manual.clicked.connect(self.manual_connect)
        dev_head.addWidget(manual)
        search = QPushButton("搜索")
        search.setObjectName("Ghost")
        search.setFixedHeight(31)
        search.setStyleSheet("padding: 4px 10px; font-size: 11.5px;")
        search.clicked.connect(self.search_devices)
        dev_head.addWidget(search)
        layout.addLayout(dev_head)

        self.device_scroll = QScrollArea()
        self.device_scroll.setWidgetResizable(True)
        self.device_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.device_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.device_scroll.setFixedHeight(132)
        self.device_body = QWidget()
        self.device_layout = QHBoxLayout(self.device_body)
        self.device_layout.setContentsMargins(0, 0, 0, 0)
        self.device_layout.setSpacing(10)
        self.device_layout.addStretch(1)
        self.device_scroll.setWidget(self.device_body)
        self.device_empty = QLabel("正在寻找设备…")
        self.device_empty.setObjectName("Muted")
        self.device_empty.setWordWrap(True)
        layout.addWidget(self.device_empty)
        layout.addWidget(self.device_scroll)

        self.dropzone = DropZone()
        self.dropzone.filesDropped.connect(self._drop_paths)
        layout.addWidget(self.dropzone)

        quick = QHBoxLayout()
        quick.setSpacing(8)
        self.pick_files_btn = QPushButton("  选择文件")
        self.pick_files_btn.setObjectName("Ghost")
        self.pick_files_btn.setIcon(make_icon("upload", palette(self.theme)["text2"], 15))
        self.pick_files_btn.clicked.connect(self.choose_files)
        self.pick_folder_btn = QPushButton("  选择文件夹")
        self.pick_folder_btn.setObjectName("Ghost")
        self.pick_folder_btn.setIcon(make_icon("folder", palette(self.theme)["text2"], 15))
        self.pick_folder_btn.clicked.connect(self.choose_folder)
        self.text_btn = QPushButton("  发送文本")
        self.text_btn.setObjectName("Ghost")
        self.text_btn.setIcon(make_icon("text", palette(self.theme)["text2"], 15))
        self.text_btn.clicked.connect(self.send_text)
        self.clip_btn = QPushButton("  剪贴板")
        self.clip_btn.setObjectName("Ghost")
        self.clip_btn.setIcon(make_icon("copy", palette(self.theme)["text2"], 15))
        self.clip_btn.clicked.connect(self.send_clipboard)
        for b in (self.pick_files_btn, self.pick_folder_btn, self.text_btn, self.clip_btn):
            b.setMinimumHeight(32)
            quick.addWidget(b)
        quick.addStretch(1)
        layout.addLayout(quick)

        self.selection_card = QFrame()
        self.selection_card.setObjectName("Card")
        selection_layout = QVBoxLayout(self.selection_card)
        selection_layout.setContentsMargins(14, 8, 14, 8)
        selection_layout.setSpacing(0)
        sel_head = QHBoxLayout()
        self.selection_title = QLabel("预传输队列")
        self.selection_title.setObjectName("SectionTitle")
        self.selection_summary = QLabel("")
        self.selection_summary.setObjectName("Muted")
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("Ghost")
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.setStyleSheet("padding: 2px 8px; font-size: 11.5px;")
        self.clear_btn.clicked.connect(self.clear_selection)
        sel_head.addWidget(self.selection_title)
        sel_head.addWidget(self.selection_summary)
        sel_head.addStretch(1)
        sel_head.addWidget(self.clear_btn)
        selection_layout.addLayout(sel_head)
        self.selection_rows = QVBoxLayout()
        self.selection_rows.setSpacing(0)
        selection_layout.addLayout(self.selection_rows)
        self.selection_card.hide()
        layout.addWidget(self.selection_card)

        send_bar = QHBoxLayout()
        self.target_label = QLabel("未选择设备")
        self.target_label.setObjectName("Muted")
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("Primary")
        self.send_btn.setIcon(make_icon("send", "#FFFFFF", 16))
        self.send_btn.setMinimumWidth(130)
        self.send_btn.setMinimumHeight(38)
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self.send_selected)
        send_bar.addWidget(self.target_label, 1)
        send_bar.addWidget(self.send_btn)

        layout.addStretch(1)
        page_layout.addWidget(scroll, 1)
        page_layout.addLayout(send_bar)
        return page

    def _build_transfers_page(self) -> QWidget:
        scroll, body, layout = self._page_scroll()
        head = QHBoxLayout()
        label = QLabel("实时传输")
        label.setObjectName("SectionTitle")
        self.transfers_note = QLabel("")
        self.transfers_note.setObjectName("Muted")
        head.addWidget(label)
        head.addWidget(self.transfers_note)
        head.addStretch(1)
        self.cancel_all_btn = QPushButton("取消全部")
        self.cancel_all_btn.setObjectName("Ghost")
        self.cancel_all_btn.setFixedHeight(30)
        self.cancel_all_btn.setStyleSheet("padding: 4px 11px; font-size: 11.5px;")
        self.cancel_all_btn.setToolTip("取消所有进行中的传输")
        self.cancel_all_btn.clicked.connect(self._cancel_all_transfers)
        self.cancel_all_btn.hide()
        head.addWidget(self.cancel_all_btn)
        layout.addLayout(head)
        self.transfers_container = QWidget()
        self.transfers_layout = QVBoxLayout(self.transfers_container)
        self.transfers_layout.setContentsMargins(0, 0, 0, 0)
        self.transfers_layout.setSpacing(9)
        self.transfers_layout.addStretch(1)
        layout.addWidget(self.transfers_container)
        self.transfers_empty = EmptyHint("refresh", "还没有传输", "", self.theme)
        layout.addWidget(self.transfers_empty)
        layout.addStretch(1)
        return scroll

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["时间", "方向", "通过", "对端", "内容", "状态"])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setShowGrid(False)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.history_table)
        self.history_empty = QLabel("还没有历史记录")
        self.history_empty.setObjectName("Muted")
        layout.addWidget(self.history_empty)
        return page

    def _build_settings_page(self) -> QWidget:
        scroll, body, layout = self._page_scroll()
        p = palette(self.theme)

        # 设备
        card, box = self._settings_card("设备", "这台电脑在局域网里的身份")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("设备名称")
        self.name_edit.setMaximumWidth(260)
        name_apply = QPushButton("保存")
        name_apply.setObjectName("Soft")
        name_apply.setFixedHeight(38)
        name_apply.clicked.connect(self.save_name)
        row = QHBoxLayout()
        row.addWidget(self.name_edit)
        row.addWidget(name_apply)
        row.addStretch(1)
        box.addLayout(row)

        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        choose_dir = QPushButton("选择目录")
        choose_dir.setObjectName("Ghost")
        choose_dir.setFixedHeight(38)
        choose_dir.clicked.connect(self.choose_download_dir)
        row2 = QHBoxLayout()
        row2.addWidget(self.dir_edit, 1)
        row2.addWidget(choose_dir)
        box.addWidget(QLabel("接收目录"))
        box.addLayout(row2)
        layout.addWidget(card)

        # 连接
        card, box = self._settings_card("连接", "HTTP 与 HTTPS 同时监听；切换只影响默认地址和电脑间传输")
        self.http_label = QLabel()
        self.http_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.https_label = QLabel()
        self.https_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        http_row = QHBoxLayout()
        http_row.addWidget(QLabel("HTTP"))
        http_row.addWidget(self.http_label, 1)
        http_copy = QPushButton("复制")
        http_copy.setObjectName("Ghost")
        http_copy.setFixedSize(48, 28)
        http_copy.setStyleSheet("padding: 2px 4px; font-size: 11.5px;")
        http_copy.clicked.connect(lambda: self._copy(self.http_label.text()))
        http_row.addWidget(http_copy)
        https_row = QHBoxLayout()
        https_row.addWidget(QLabel("HTTPS"))
        https_row.addWidget(self.https_label, 1)
        https_copy = QPushButton("复制")
        https_copy.setObjectName("Ghost")
        https_copy.setFixedSize(48, 28)
        https_copy.setStyleSheet("padding: 2px 4px; font-size: 11.5px;")
        https_copy.clicked.connect(lambda: self._copy(self.https_label.text()))
        https_row.addWidget(https_copy)
        box.addLayout(http_row)
        box.addLayout(https_row)
        self.https_check = QCheckBox("优先使用 HTTPS")
        self.https_check.clicked.connect(self.toggle_prefer_https)
        box.addWidget(self.https_check)
        self.tls_label = QLabel()
        self.tls_label.setObjectName("Small")
        self.tls_label.setWordWrap(True)
        box.addWidget(self.tls_label)
        layout.addWidget(card)

        # 安全
        card, box = self._settings_card("安全与接收", "默认手动确认；也可以设置 PIN 或自动接收")
        self.auto_check = QCheckBox("自动接受其他设备的传输")
        self.auto_check.clicked.connect(self.toggle_auto_accept)
        box.addWidget(self.auto_check)
        pin_row = QHBoxLayout()
        self.pin_edit = QLineEdit()
        self.pin_edit.setPlaceholderText("PIN")
        self.pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_edit.setMaximumWidth(190)
        pin_apply = QPushButton("保存 PIN")
        pin_apply.setObjectName("Ghost")
        pin_apply.setFixedHeight(38)
        pin_apply.clicked.connect(self.save_pin)
        pin_row.addWidget(self.pin_edit)
        pin_row.addWidget(pin_apply)
        pin_row.addStretch(1)
        box.addLayout(pin_row)
        pair_row = QHBoxLayout()
        self.pair_label = QLabel()
        self.pair_label.setStyleSheet(f"font-size: 18px; font-weight: 700; letter-spacing: 3px; color:{p['accent']};")
        rotate = QPushButton("轮换配对码")
        rotate.setObjectName("Ghost")
        rotate.setFixedHeight(38)
        rotate.clicked.connect(self.rotate_pair)
        qr = QPushButton("显示二维码")
        qr.setObjectName("Soft")
        qr.setFixedHeight(38)
        qr.clicked.connect(self.show_qr)
        pair_row.addWidget(QLabel("网页配对码"))
        pair_row.addWidget(self.pair_label)
        pair_row.addStretch(1)
        pair_row.addWidget(rotate)
        pair_row.addWidget(qr)
        box.addLayout(pair_row)
        layout.addWidget(card)

        # 外观
        card, box = self._settings_card("外观与启动", "深浅色可在窗口右上角一键切换；关闭窗口默认驻留托盘")
        self.startup_check = QCheckBox("开机自动启动")
        self.startup_check.clicked.connect(self.toggle_startup)
        box.addWidget(self.startup_check)
        shell = QPushButton("资源管理器右键")
        shell.setObjectName("Ghost")
        shell.setFixedHeight(38)
        shell.clicked.connect(self.register_shell)
        box.addWidget(shell)
        firewall = QPushButton("配置 Windows 防火墙")
        firewall.setObjectName("Ghost")
        firewall.setFixedHeight(38)
        firewall.clicked.connect(self.firewall_flow)
        box.addWidget(firewall, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(card)

        # 关于
        card, box = self._settings_card("关于与更新")
        self.about_label = QLabel(f"{APP_NAME} · {APP_CN}  v{VERSION}")
        self.about_label.setObjectName("Muted")
        box.addWidget(self.about_label)
        update_row = QHBoxLayout()
        self.update_status = QLabel("点击检查更新，获取最新版本")
        self.update_status.setObjectName("Muted")
        self.update_status.setWordWrap(True)
        self.update_btn = QPushButton("检查更新")
        self.update_btn.setObjectName("Soft")
        self.update_btn.setFixedHeight(34)
        self.update_btn.clicked.connect(lambda: self.check_updates(manual=True))
        self.update_download = QPushButton("下载新版")
        self.update_download.setObjectName("Primary")
        self.update_download.setFixedHeight(34)
        self.update_download.hide()
        self.update_download.clicked.connect(self.open_update_page)
        update_row.addWidget(self.update_status, 1)
        update_row.addWidget(self.update_btn)
        update_row.addWidget(self.update_download)
        box.addLayout(update_row)
        github = QLabel(
            f'GitHub&nbsp;&nbsp;<a style="color:{p["accent"]}; text-decoration:none;" '
            'href="https://github.com/JASON-SHEN-0225/Aster">JASON-SHEN-0225/Aster</a>'
        )
        github.setOpenExternalLinks(True)
        github.setTextFormat(Qt.TextFormat.RichText)
        github.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.addWidget(github)
        email = QLabel(
            f'邮箱&nbsp;&nbsp;<a style="color:{p["accent"]}; text-decoration:none;" '
            'href="mailto:jasonshen0225@163.com">jasonshen0225@163.com</a>'
        )
        email.setOpenExternalLinks(True)
        email.setTextFormat(Qt.TextFormat.RichText)
        email.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.addWidget(email)
        layout.addWidget(card)
        layout.addStretch(1)
        return scroll

    def _settings_card(self, title: str, sub: str = "") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("SectionTitle")
        box.addWidget(t)
        return card, box

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------
    def _start_timers(self) -> None:
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(600)
        self.refresh_timer.timeout.connect(self._refresh)
        self.refresh_timer.start()

    def _after_show(self) -> None:
        if self._minimized:
            self.hide()
            if self.tray:
                self.tray.showMessage(APP_NAME, "Aster 正在后台运行", QSystemTrayIcon.MessageIcon.Information, 2500)
        else:
            self.show()

    def search_devices(self) -> None:
        self.node.refresh_discovery()
        self._refresh()
        self.toast("正在搜索附近设备")

    def _refresh(self) -> None:
        try:
            state = self.node.snapshot()
        except Exception:
            return
        p = palette(self.theme)
        self.conn_pill.setText("在线")
        self.conn_pill.setStyleSheet(
            f"background:{p['mint_soft']}; color:{p['mint']}; border-radius:11px; padding:4px 11px; font-size:14px; font-weight:650;"
        )
        if self.node.tls_material:
            prefer = bool(self.config.prefer_https)
            self.scheme_switch.set_prefer(prefer)
            self.scheme_switch.setToolTip("切换 HTTP / HTTPS 优先")
        else:
            self.scheme_switch.set_prefer(False)
            self.scheme_switch.setEnabled(False)
            self.scheme_switch.setToolTip("HTTPS 当前不可用")
        self.hero_meta.setText(
            f"{self.config.alias}  ·  {self.node.lan_ip}:{self.node.port}  ·  "
            f"{'HTTPS 可用' if self.node.tls_material else 'HTTP'}  ·  {VERSION}"
        )
        self.local_info.setText(
            f"{self.config.alias}\n{self.node.lan_ip}:{self.node.port}\n"
            f"HTTP {self.node.port} · HTTPS {self.node.https_port}"
        )
        self._refresh_devices(state)
        self._refresh_transfers(state)
        self._refresh_web_state(state)
        self._refresh_settings_dynamic()
        self._refresh_send_button()
        self._check_send_done()
        self._refresh_history_if_needed()
        self._handle_pending()
        self._notify_transfers(state)
        self._drain_external_queue()
        if self.tray:
            active = sum(
                1
                for t in state.get("transfers", [])
                if t.get("status") in ("waiting", "active", "uploading", "verifying")
            )
            self.tray.setToolTip(
                f"{APP_NAME} · {self.config.alias}\n"
                f"HTTP {self.node.port} · HTTPS {self.node.https_port}\n"
                f"{active} 个传输进行中"
            )

    def _refresh_devices(self, state: dict[str, Any]) -> None:
        peers = [p for p in state.get("peers", []) if p.get("online")]
        webs = [w for w in state.get("web_sessions", []) if w.get("online")]
        items: list[tuple[str, dict[str, Any]]] = []
        for peer in peers:
            items.append(("peer", peer))
        for ws in webs:
            item = dict(ws)
            client = str(ws.get("client") or "web").lower()
            item["client"] = client
            item["id"] = f"web:{ws.get('id')}"
            item["alias"] = ws.get("name") or ("手机" if client == "apk" else "网页端设备")
            item["device_type"] = "web"
            item["_web_id"] = ws.get("id")
            items.append(("web", item))
        signature = tuple(
            (
                kind,
                str(obj.get("id")),
                str(obj.get("alias") or obj.get("name")),
                obj.get("online"),
                obj.get("ip"),
                obj.get("client"),
            )
            for kind, obj in items
        )
        if signature == self.device_signature:
            return
        self.device_signature = signature
        for card in self.device_cards.values():
            card.setParent(None)
            card.deleteLater()
        self.device_cards.clear()
        # remove stretch
        while self.device_layout.count():
            item = self.device_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not items:
            self.device_empty.show()
            self.device_scroll.hide()
            self.device_layout.addStretch(1)
            self.target = None
            self.target_kind = ""
            self.target_label.setText("未选择设备")
            return
        self.device_empty.hide()
        self.device_scroll.show()
        for kind, obj in items:
            card = DeviceCard(obj, self.theme)
            key = str(obj.get("id"))
            card.clicked.connect(lambda peer, k=kind: self.select_target(k, peer))
            if self.target and str(self.target.get("id")) == key:
                card.set_selected(True)
            self.device_cards[key] = card
            self.device_layout.addWidget(card)
        self.device_layout.addStretch(1)
        if self.target:
            self.target = next(
                (obj for kind, obj in items if str(obj.get("id")) == str(self.target.get("id"))),
                None,
            )
            if not self.target:
                self.target_kind = ""
                self.target_label.setText("未选择设备")
        self._refresh_target_label()

    def _refresh_web_state(self, state: dict[str, Any]) -> None:
        online = [w for w in state.get("web_sessions", []) if w.get("online")]
        if online:
            names = "、".join(
                str(w.get("name") or ("手机" if str(w.get("client") or "web").lower() == "apk" else "网页端设备"))
                for w in online[:2]
            )
            self.web_state.setText(f"{len(online)} 个在线 · {names}")
        else:
            self.web_state.setText("等待手机连接")
        self.pair_label.setText(self.config.web_pair_code if self.config.web_pairing else "已关闭")

    def _refresh_transfers(self, state: dict[str, Any]) -> None:
        transfers = state.get("transfers", [])
        items = [
            t for t in transfers
            if t.get("status") in ("waiting", "pending", "active", "uploading", "verifying", "finalizing")
        ]
        recent = [t for t in transfers if t.get("status") not in ("waiting", "pending", "active", "uploading", "verifying", "finalizing")][:4]
        items = items + recent
        signature = tuple(
            (t.get("id"), t.get("status"), t.get("done_bytes"), t.get("current_file"), t.get("error"))
            for t in items
        )
        if signature == self.transfer_signature:
            return
        self.transfer_signature = signature
        # remove old cards not in items
        ids = {str(t.get("id")) for t in items}
        for tid in list(self.transfer_cards):
            if tid not in ids:
                card = self.transfer_cards.pop(tid)
                self.transfers_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()
        for t in items:
            tid = str(t.get("id"))
            card = self.transfer_cards.get(tid)
            if card is None:
                card = TransferCard(t, self.theme)
                card.cancelClicked.connect(self._cancel_transfer)
                self.transfer_cards[tid] = card
                self.transfers_layout.insertWidget(self.transfers_layout.count() - 1, card)
            else:
                card.update_transfer(t, self.theme)
        self.transfers_empty.setVisible(not items)
        active = len(
            [
                t for t in items
                if t.get("status") in ("waiting", "pending", "active", "uploading", "verifying", "finalizing")
            ]
        )
        self.transfers_note.setText(f"{active} 个进行中" if active else "")
        self.cancel_all_btn.setVisible(active > 0)

    def _notify_transfers(self, state: dict[str, Any]) -> None:
        if not self.tray:
            return
        for t in state.get("transfers", []):
            if t.get("status") != "completed":
                continue
            tid = str(t.get("id"))
            if tid in self._notified_transfers:
                continue
            self._notified_transfers.add(tid)
            if t.get("via") == "web" and t.get("direction") == "in":
                self.tray.showMessage(APP_NAME, f"已接收：{self._transfer_title(t)}", QSystemTrayIcon.MessageIcon.Information, 2500)

    @staticmethod
    def _transfer_title(t: dict[str, Any]) -> str:
        files = t.get("files") or []
        if files:
            name = files[0].get("name") or "文件"
            return name + (f" 等 {len(files)} 个" if len(files) > 1 else "")
        return "文本"

    def _refresh_history_if_needed(self) -> None:
        if self.stack.currentIndex() != PAGE_HISTORY:
            return
        self.history_counter += 1
        if self.history_counter % 2 != 0:
            return
        self._load_history()

    def _load_history(self) -> None:
        items = self.node.public_history(80)
        self.history_table.setRowCount(len(items))
        p = palette(self.theme)
        for row, item in enumerate(items):
            files = item.get("files") or []
            content = files[0].get("name") if files else (item.get("text") or "")
            if len(files) > 1:
                content = f"{content} 等 {len(files)} 个"
            values = [
                format_time(item.get("started_at")),
                "发送" if item.get("direction") == "out" else "接收",
                (
                    "电脑"
                    if item.get("via") != "web"
                    else (
                        "APK"
                        if str((item.get("peer") or {}).get("client") or "").lower() == "apk"
                        else "网页"
                    )
                ),
                str((item.get("peer") or {}).get("alias") or "-"),
                str(content),
                STATUS_TEXT.get(str(item.get("status")), str(item.get("status") or "-")),
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                if col == 5:
                    if item.get("status") == "completed":
                        cell.setForeground(QBrush(QColor(p["mint"])))
                    elif item.get("status") in ("failed", "rejected"):
                        cell.setForeground(QBrush(QColor(p["danger"])))
                self.history_table.setItem(row, col, cell)
        self.history_empty.setVisible(not items)

    def _refresh_settings_state(self) -> None:
        if self._loading_settings:
            return
        self._loading_settings = True
        try:
            self.name_edit.setText(self.config.alias)
            self.dir_edit.setText(self.config.download_dir)
            self.http_label.setText(self.node.web_url(https=False))
            self.https_label.setText(self.node.web_url(https=True) if self.node.tls_material else "不可用")
            self.https_check.setChecked(bool(self.config.prefer_https and self.node.tls_material))
            self.https_check.setEnabled(bool(self.node.tls_material))
            if self.node.tls_material:
                self.tls_label.setText(
                    f"TLS 指纹：{self.node.tls_material.fingerprint[:32]}  ·  "
                    f"HTTPS 端口 {self.node.https_port}"
                )
            else:
                self.tls_label.setText(f"HTTPS 不可用：{self.node.tls_error or '证书未启动'}")
            self.auto_check.setChecked(bool(self.config.auto_accept))
            self.pin_edit.setText(self.config.pin)
            self.pair_label.setText(self.config.web_pair_code if self.config.web_pairing else "已关闭")
            self.startup_check.setChecked(self._startup_enabled())
        finally:
            self._loading_settings = False

    def _refresh_settings_dynamic(self) -> None:
        """只刷新会在外部变化的标签/开关，避免覆盖用户正在输入的内容。"""
        if not hasattr(self, "https_label"):
            return
        was = self._loading_settings
        self._loading_settings = True
        try:
            self.http_label.setText(self.node.web_url(https=False))
            self.https_label.setText(self.node.web_url(https=True) if self.node.tls_material else "不可用")
            self.https_check.setEnabled(bool(self.node.tls_material))
            self.https_check.setChecked(bool(self.config.prefer_https and self.node.tls_material))
            self.auto_check.setChecked(bool(self.config.auto_accept))
            self.pair_label.setText(self.config.web_pair_code if self.config.web_pairing else "已关闭")
            if self.node.tls_material:
                self.tls_label.setText(
                    f"TLS 指纹：{self.node.tls_material.fingerprint[:32]}  ·  "
                    f"HTTPS 端口 {self.node.https_port}"
                )
            else:
                self.tls_label.setText(f"HTTPS 不可用：{self.node.tls_error or '证书未启动'}")
        finally:
            self._loading_settings = was

    # ------------------------------------------------------------------
    # 设备/选择
    # ------------------------------------------------------------------
    def select_target(self, kind: str, obj: dict[str, Any]) -> None:
        self.target = obj
        self.target_kind = kind
        key = str(obj.get("id"))
        for cid, card in self.device_cards.items():
            card.set_selected(cid == key)
        self._refresh_target_label()

    def _refresh_target_label(self) -> None:
        if self.target:
            name = self.target.get("alias") or self.target.get("name") or "设备"
            if self.target_kind == "web":
                kind = "APK 手机" if str(self.target.get("client") or "web") == "apk" else "网页端"
            else:
                kind = "电脑"
            self.target_label.setText(f"目标：{name}（{kind}）")
        else:
            self.target_label.setText("未选择设备")
        self._refresh_send_button()

    def _refresh_send_button(self) -> None:
        ok = bool(self.target and self.selected_paths and not self.send_busy)
        self.send_btn.setEnabled(ok)
        self.send_btn.setText("发送中…" if self.send_busy else "发送")

    def _drain_external_queue(self) -> None:
        try:
            paths = self.inbox.drain()
        except Exception:
            return
        if not paths:
            return
        before = len(self.selected_paths)
        added = self._add_paths(paths)
        if not added:
            return
        self.show_page(PAGE_SEND)
        if self.isHidden() or self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self.toast(f"已加入预传输队列：{added} 项")
        if self.tray:
            self.tray.showMessage(
                APP_NAME,
                f"{added} 项已加入预传输队列",
                QSystemTrayIcon.MessageIcon.Information,
                2200,
            )

    def register_shell(self) -> None:
        ok, message = register_shell_menu()
        self.toast(message if ok else f"注册失败：{message}")

    def _add_paths(self, paths: list[str]) -> int:
        added = 0
        for raw in paths:
            path = str(Path(raw).expanduser().resolve())
            if not os.path.exists(path):
                continue
            if path in self.selected_paths:
                continue
            self.selected_paths.append(path)
            added += 1
        if not added:
            return 0
        self._recompute_selection()
        self._refresh_send_button()
        return added

    def _drop_paths(self, paths: list[str]) -> None:
        if paths:
            self._add_paths(paths)
        else:
            self.choose_files()

    def _recompute_selection(self) -> None:
        while self.selection_rows.count():
            item = self.selection_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.selection_files = []
        total = 0
        if self.selected_paths:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self.selection_files = expand_paths(self.selected_paths)
                total = sum(int(f.get("size") or 0) for f in self.selection_files)
            except Exception as exc:
                QMessageBox.warning(self, "无法添加", str(exc))
                self.selected_paths = []
                self.selection_files = []
                total = 0
            finally:
                QApplication.restoreOverrideCursor()
        for root in self.selected_paths:
            p = Path(root)
            size = 0
            if p.is_file():
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
            row = FileRow(root, size, self.theme)
            row.removeClicked.connect(self._remove_path)
            self.selection_rows.addWidget(row)
        self.selection_card.setVisible(bool(self.selected_paths))
        if self.selection_files:
            self.selection_title.setText("预传输队列")
            self.selection_summary.setText(
                f"{len(self.selection_files)} 个文件 · {human_size(total)}"
            )
        elif self.selected_paths:
            self.selection_title.setText("预传输队列")
            self.selection_summary.setText(f"{len(self.selected_paths)} 项")
        self._refresh_send_button()

    def _remove_path(self, path: str) -> None:
        if path in self.selected_paths:
            self.selected_paths.remove(path)
        self._recompute_selection()

    def clear_selection(self) -> None:
        self.selected_paths = []
        self.selection_files = []
        while self.selection_rows.count():
            item = self.selection_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.selection_card.hide()
        self._refresh_send_button()

    def choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", str(Path.home()))
        if files:
            self._add_paths(files)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", str(Path.home()))
        if folder:
            self._add_paths([folder])

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------
    def send_selected(self) -> None:
        if self.send_busy:
            return
        if not self.target:
            self.toast("先选择一个目标设备")
            return
        if not self.selected_paths:
            self.toast("先选择文件")
            return
        pin = ""
        if self.target.get("requires_pin"):
            dlg = InputDialog("接收 PIN", "对方设置了接收 PIN", self.theme, password=True, parent=self)
            if dlg.exec() != InputDialog.DialogCode.Accepted:
                return
            pin = dlg.value()
            if not pin:
                return
        paths = list(self.selected_paths)
        if self.target_kind == "web":
            try:
                result = self.node.send_to_web(str(self.target.get("_web_id")), paths)
                self.toast(f"已推送到 {self.target.get('alias')}")
                self.clear_selection()
            except Exception as exc:
                QMessageBox.warning(self, "发送失败", str(exc))
            return
        self._start_send(self.target, paths, "", pin)

    def send_text(self) -> None:
        if not self.target:
            self.toast("先选择一个目标设备")
            return
        name = self.target.get("alias") or self.target.get("name") or "设备"
        dlg = TextDialog(name, self.theme, self)
        if dlg.exec() != TextDialog.DialogCode.Accepted:
            return
        value = dlg.text()
        if not value:
            return
        if self.target_kind == "web":
            try:
                self.node.send_to_web(str(self.target.get("_web_id")), [], text=value)
                self.toast("文本已推送")
            except Exception as exc:
                QMessageBox.warning(self, "发送失败", str(exc))
            return
        self._start_send(self.target, [], value, "")

    def send_clipboard(self) -> None:
        if not self.target:
            self.toast("先选择一个目标设备")
            return
        value = get_clipboard_text()
        if not value:
            self.toast("剪贴板为空")
            return
        if self.target_kind == "web":
            try:
                self.node.send_to_web(str(self.target.get("_web_id")), [], text=value)
                self.toast("剪贴板已推送")
            except Exception as exc:
                QMessageBox.warning(self, "发送失败", str(exc))
            return
        self._start_send(self.target, [], value, "")

    def _start_send(self, target: dict[str, Any], paths: list[str], text: str, pin: str) -> None:
        self.send_busy = True
        self.send_result = None
        self.send_summary = text if text else f"{len(paths)} 项"

        def work() -> None:
            try:
                self.send_result = self.node.send_to_peer(
                    target,
                    paths,
                    text=text,
                    pin=pin,
                )
            except Exception as exc:
                self.send_result = {
                    "status": "failed",
                    "error": str(exc),
                    "files": [],
                    "total_bytes": 0,
                }

        self.send_thread = threading.Thread(target=work, name="aster-gui-send", daemon=True)
        self.send_thread.start()
        self.send_btn.setEnabled(False)
        self.send_btn.setText("发送中…")
        self.statusBar().showMessage("正在发送，等待对方确认…")
        self.show_page(PAGE_TRANSFERS)

    def _check_send_done(self) -> None:
        if not self.send_busy or not self.send_thread or self.send_thread.is_alive():
            return
        result = self.send_result or {}
        self.send_busy = False
        self.send_thread = None
        self.send_result = None
        self._refresh_send_button()
        status = str(result.get("status") or "failed")
        if status == "completed":
            self.toast("发送完成")
            self.statusBar().showMessage("发送完成", 5000)
            self.clear_selection()
            if self.tray:
                self.tray.showMessage(APP_NAME, "发送完成", QSystemTrayIcon.MessageIcon.Information, 1800)
        elif status == "cancelled":
            self.toast("已取消发送")
        elif status == "rejected":
            self.toast(result.get("error") or "对方拒绝了传输")
        else:
            self.toast(result.get("error") or "发送失败")
        self._refresh()

    def _cancel_transfer(self, transfer_id: str) -> None:
        try:
            self.node.cancel_transfer(transfer_id)
            self.toast("已取消任务")
        except Exception as exc:
            self.toast(str(exc) or "取消失败")
        self._refresh()

    def _cancel_all_transfers(self) -> None:
        try:
            results = self.node.cancel_all_transfers()
            self.toast(f"已取消 {len(results)} 个任务" if results else "没有可取消的任务")
        except Exception as exc:
            self.toast(str(exc) or "取消失败")
        self._refresh()

    # ------------------------------------------------------------------
    # 接收确认
    # ------------------------------------------------------------------
    def _handle_pending(self) -> None:
        if self._pending_open:
            return
        pending = self.node.list_pending()
        if not pending:
            return
        item = pending[0]
        self._pending_open = True
        if self.tray:
            peer = (item.get("peer") or {}).get("alias") or "设备"
            self.tray.showMessage(APP_NAME, f"{peer} 发来传输请求", QSystemTrayIcon.MessageIcon.Information, 2800)
        try:
            dlg = ReceiveDialog(item, self.theme, self)
            result = dlg.exec()
            self.node.decide_pending(str(item.get("id")), result == ReceiveDialog.DialogCode.Accepted)
            if result == ReceiveDialog.DialogCode.Accepted:
                self.toast("已接受传输")
            else:
                self.toast("已拒绝传输")
        finally:
            self._pending_open = False

    # ------------------------------------------------------------------
    # 设置操作
    # ------------------------------------------------------------------
    def save_name(self) -> None:
        try:
            self.node.set_alias(self.name_edit.text())
            self.toast("设备名称已保存")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def choose_download_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择接收目录", self.config.download_dir)
        if not folder:
            return
        self.config.download_dir = str(Path(folder).resolve())
        self.node.store.save()
        self.dir_edit.setText(self.config.download_dir)
        self.toast("接收目录已更新")

    def toggle_prefer_https(self, checked: bool | None = None) -> None:
        if self._loading_settings:
            return
        enabled = self.https_check.isChecked() if checked is None else bool(checked)
        try:
            self.node.set_prefer_https(enabled)
            self.toast("已优先使用 HTTPS" if enabled else "已切回 HTTP 优先")
        except ValueError as exc:
            QMessageBox.warning(self, "HTTPS 不可用", str(exc))
            self._refresh_settings_state()
        self._refresh()

    def toggle_auto_accept(self) -> None:
        if self._loading_settings:
            return
        self.node.set_auto_accept(self.auto_check.isChecked())
        self.toast("已开启自动接受" if self.auto_check.isChecked() else "已关闭自动接受")

    def save_pin(self) -> None:
        pin = self.pin_edit.text().strip()
        if pin and not (4 <= len(pin) <= 8 and pin.isdigit()):
            QMessageBox.warning(self, "PIN 无效", "PIN 需要 4-8 位数字，留空表示关闭。")
            return
        self.config.pin = pin
        self.node.store.save()
        self.toast("PIN 已更新" if pin else "PIN 已关闭")

    def rotate_pair(self) -> None:
        code = self.node.rotate_pair_code()
        self.pair_label.setText(code)
        self.toast(f"新的配对码：{code}")

    def toggle_theme(self, dark: bool) -> None:
        self.apply_theme("dark" if dark else "light")

    # ------------------------------------------------------------------
    # 检查更新
    # ------------------------------------------------------------------
    def check_updates(self, manual: bool = False) -> None:
        if self._update_busy:
            return
        if not manual and self._update_checked:
            return
        self._update_busy = True
        self.update_btn.setEnabled(False)
        if manual:
            self.update_status.setText("正在检查更新…")

        def work() -> None:
            try:
                result = self.node.check_update(force=manual)
            except Exception as exc:
                result = {
                    "ok": False,
                    "error": str(exc),
                    "current": {"desktop": VERSION},
                    "latest": None,
                }
            result["_manual"] = manual
            self.update_checked.emit(result)

        threading.Thread(target=work, name="aster-update-check", daemon=True).start()

    def _apply_update_result(self, result: dict[str, Any]) -> None:
        self._update_busy = False
        self._update_checked = True
        self.update_btn.setEnabled(True)
        manual = bool(result.get("_manual"))
        latest = result.get("latest") if isinstance(result.get("latest"), dict) else None
        desktop = (latest or {}).get("desktop") if isinstance(latest, dict) else None
        latest_version = str((latest or {}).get("version") or "")
        newer = bool(
            desktop
            and str(desktop.get("version") or latest_version)
            and str(desktop.get("version") or latest_version) != VERSION
        )
        if newer:
            from ..update import is_newer

            newer = is_newer(desktop.get("version") or latest_version, VERSION)
        if not result.get("ok") or latest is None:
            self.update_status.setText("无法检查更新，请稍后重试")
            self.update_download.hide()
            if manual:
                self.toast("无法检查更新")
            return
        if newer:
            version = str(desktop.get("version") or latest_version)
            self.update_status.setText(f"发现新版本 {version}")
            from ..update import DOWNLOAD_PAGE

            self._update_url = str((latest or {}).get("page") or DOWNLOAD_PAGE)
            self.update_download.show()
            if manual:
                self.toast(f"发现新版本 {version}")
            elif self.tray:
                self.tray.showMessage(
                    APP_NAME,
                    f"发现新版本 {version}，可在设置中下载",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
        else:
            self.update_status.setText(f"已是最新版本 v{VERSION}")
            self.update_download.hide()
            if manual:
                self.toast("已是最新版本")

    def open_update_page(self) -> None:
        try:
            from ..update import DOWNLOAD_PAGE

            url = self._update_url or DOWNLOAD_PAGE
        except Exception:
            url = self._update_url
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def apply_theme(self, theme: str) -> None:
        theme = "dark" if theme == "dark" else "light"
        self.theme = theme
        self.config.theme = theme
        self.node.store.save()
        QApplication.instance().setStyleSheet(build_qss(theme))
        self.hero_logo.set_theme(theme)
        self.hero_title.set_theme(theme)
        self.theme_switch.set_dark(theme == "dark", animate=False)
        self._apply_icons()
        self.device_signature = ()
        self.transfer_signature = ()
        self._refresh()
        if self._toast:
            self._toast.reposition()

    def _apply_icons(self) -> None:
        p = palette(self.theme)
        for btn in self.nav_buttons:
            icon_id = str(btn.property("iconId") or "star")
            color = p["accent"] if btn.isChecked() else p["text2"]
            btn.setIcon(make_icon(icon_id, color, 17))
            btn.setIconSize(QSize(17, 17))
        self.pick_files_btn.setIcon(make_icon("upload", p["text2"], 15))
        self.pick_folder_btn.setIcon(make_icon("folder", p["text2"], 15))
        self.text_btn.setIcon(make_icon("text", p["text2"], 15))
        self.clip_btn.setIcon(make_icon("copy", p["text2"], 15))
        self.refresh_btn.setIcon(make_icon("refresh", p["text2"], 15))
        self.send_btn.setIcon(make_icon("send", "#FFFFFF", 16))
        self.brand_logo.setPixmap(make_icon("star", p["accent"], 30).pixmap(30, 30))
        self.brand_logo.setStyleSheet(f"background:{p['accent_soft']}; border-radius:11px;")
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background:{p['bg']}; color:{p['text3']}; font-size:12px; }}"
        )

    def _startup_enabled(self) -> bool:
        if os.name != "nt":
            return False
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
            )
            try:
                value, _ = winreg.QueryValueEx(key, "Aster")
                return bool(value)
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    def toggle_startup(self) -> None:
        if self._loading_settings:
            return
        enabled = self.startup_check.isChecked()
        try:
            if os.name != "nt":
                self.toast("仅 Windows 支持开机自启")
                return
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                if enabled:
                    if getattr(sys, "frozen", False):
                        cmd = f'"{sys.executable}" --minimized'
                    else:
                        pythonw = Path(sys.executable).with_name("pythonw.exe")
                        entry = Path(sys.argv[0]).resolve()
                        cmd = f'"{pythonw}" "{entry}" --minimized'
                    winreg.SetValueEx(key, "Aster", 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, "Aster")
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
            self.toast("已开启开机自启" if enabled else "已关闭开机自启")
        except Exception as exc:
            QMessageBox.warning(self, "设置失败", str(exc))

    def firewall_flow(self) -> None:
        from ..firewall import add_firewall_rules, request_elevation

        ok, msg = add_firewall_rules(self.node.port, self.node.https_port)
        if ok:
            QMessageBox.information(
                self,
                "防火墙",
                f"已添加 TCP {self.node.port}/{self.node.https_port} 与 UDP {self.node.port} 规则。",
            )
            return
        answer = QMessageBox.question(
            self,
            "需要管理员权限",
            msg + "\n\n是否弹出 UAC 以管理员身份添加防火墙规则？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            ok2, msg2 = request_elevation(self.node.port, self.node.https_port)
            QMessageBox.information(self, "防火墙", msg2)

    # ------------------------------------------------------------------
    # 网页 / 二维码
    # ------------------------------------------------------------------
    def show_qr(self) -> None:
        QRDialog(self.node, self.theme, self).exec()

    def open_web(self) -> None:
        QDesktopServices.openUrl(QUrl(self.node.pair_url()))

    def manual_connect(self) -> None:
        dlg = InputDialog(
            "连接 IP",
            "对方 IP",
            self.theme,
            placeholder="192.168.1.8:47820",
            parent=self,
        )
        if dlg.exec() != InputDialog.DialogCode.Accepted:
            return
        raw = dlg.value()
        if not raw:
            return
        host, port = raw, self.config.port
        if ":" in raw:
            host, p = raw.rsplit(":", 1)
            if p.isdigit():
                port = int(p)
        try:
            info = PeerClient(host, port).info()
            peer = self.node.remember_peer(info, host, port)
            self._refresh()
            self.toast(f"已连接 {peer.get('alias') or host}")
        except PeerError as exc:
            QMessageBox.warning(self, "连接失败", str(exc))

    def _copy(self, value: str) -> None:
        QApplication.clipboard().setText(value)
        self.toast("已复制")

    # ------------------------------------------------------------------
    # 页面 / 托盘
    # ------------------------------------------------------------------
    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self._set_page_titles(index)
        if index == PAGE_HISTORY:
            self._load_history()
        if index == PAGE_SETTINGS:
            self._refresh_settings_state()
        self._apply_icons()
        widget = self.stack.currentWidget()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(170)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start()
        self._page_anim = anim

    def _set_page_titles(self, index: int) -> None:
        titles = {
            PAGE_SEND: "发送",
            PAGE_TRANSFERS: "传输",
            PAGE_HISTORY: "历史",
            PAGE_SETTINGS: "设置",
        }
        self.page_title.setText(titles.get(index, "发送"))
        self.page_sub.setText("")

    def _build_tray(self) -> None:
        self.tray: Optional[QSystemTrayIcon] = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} · {APP_CN}")
        menu = QMenu()
        show = QAction("显示 Aster", self)
        show.triggered.connect(self.show_normal)
        send = QAction("发送文件…", self)
        send.triggered.connect(lambda: (self.show_normal(), self.choose_files()))
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show)
        menu.addAction(send)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_normal()

    def show_normal(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def toast(self, message: str) -> None:
        if self._toast is None:
            self._toast = Toast(self, message)
        else:
            self._toast.show_message(message)
        self._toast.reposition()
        self._toast.show()
        self._toast.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._toast and self._toast.isVisible():
            self._toast.reposition()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._quitting or not self.tray:
            event.accept()
            return
        event.ignore()
        self.hide()
        if self._first_close:
            self._first_close = False
            self.tray.showMessage(
                APP_NAME,
                "Aster 仍在后台运行",
                QSystemTrayIcon.MessageIcon.Information,
                2800,
            )
