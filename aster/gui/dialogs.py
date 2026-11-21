"""Aster GUI 对话框。"""

from __future__ import annotations

import io
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .icons import make_icon
from .theme import palette
from ..util import human_size, truncate


class BaseDialog(QDialog):
    def __init__(self, parent: Optional[QWidget], title: str, theme: str, width: int = 480):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        self.setWindowIcon(parent.windowIcon() if parent else None)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 20, 22, 18)
        self.root.setSpacing(14)


class ReceiveDialog(BaseDialog):
    def __init__(self, pending: dict[str, Any], theme: str, parent: Optional[QWidget] = None):
        super().__init__(parent, "传输请求", theme, 540)
        p = palette(theme)
        self.pending = pending
        peer = pending.get("peer") or {}
        name = peer.get("alias") or peer.get("ip") or "未知设备"

        head = QHBoxLayout()
        avatar = QLabel()
        avatar.setFixedSize(42, 42)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setPixmap(make_icon("monitor", p["accent"], 22).pixmap(22, 22))
        avatar.setStyleSheet(f"background:{p['accent_soft']}; border-radius:11px;")
        head.addWidget(avatar)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        t = QLabel(f"{name} 想发送内容")
        t.setStyleSheet("font-size: 16px; font-weight: 650;")
        sub = QLabel(f"{peer.get('ip') or '局域网'} · {pending.get('remaining') or pending.get('expires_in', 0)} 秒内确认")
        sub.setObjectName("Muted")
        copy.addWidget(t)
        copy.addWidget(sub)
        head.addLayout(copy, 1)
        self.root.addLayout(head)

        files = pending.get("files") or []
        if files:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setMaximumHeight(190)
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            box_layout.setSpacing(0)
            total = 0
            for f in files:
                total += int(f.get("size") or 0)
                row = QFrame()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(7, 6, 7, 6)
                icon = QLabel()
                icon.setPixmap(make_icon("text", p["text3"], 15).pixmap(15, 15))
                row_layout.addWidget(icon)
                label = QLabel(str(f.get("rel_path") or f.get("name") or "文件"))
                label.setStyleSheet("font-size: 12px;")
                label.setToolTip(str(f.get("rel_path") or f.get("name") or ""))
                row_layout.addWidget(label, 1)
                size = QLabel(human_size(f.get("size")))
                size.setObjectName("Small")
                row_layout.addWidget(size)
                box_layout.addWidget(row)
            box_layout.addStretch(1)
            scroll.setWidget(box)
            self.root.addWidget(scroll)
            total_label = QLabel(f"共 {len(files)} 个文件 · {human_size(total)}")
            total_label.setObjectName("Muted")
            self.root.addWidget(total_label)
        text = str(pending.get("text") or "")
        if text:
            preview = QTextEdit()
            preview.setReadOnly(True)
            preview.setPlainText(text)
            preview.setMaximumHeight(100)
            self.root.addWidget(preview)

        self.tip = QLabel("")
        self.tip.hide()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        reject = QPushButton("拒绝")
        reject.setObjectName("Ghost")
        reject.clicked.connect(self.reject)
        accept = QPushButton("接收")
        accept.setObjectName("Primary")
        accept.clicked.connect(self.accept)
        buttons.addWidget(reject)
        buttons.addWidget(accept)
        self.root.addLayout(buttons)


class TextDialog(BaseDialog):
    def __init__(self, target_name: str, theme: str, parent: Optional[QWidget] = None):
        super().__init__(parent, "发送文本", theme, 520)
        p = palette(theme)
        title = QLabel("发送文本到电脑")
        title.setStyleSheet("font-size: 17px; font-weight: 650;")
        target = QLabel(f"目标：{target_name}")
        target.setObjectName("Muted")
        self.root.addWidget(title)
        self.root.addWidget(target)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("文本")
        self.editor.setMinimumHeight(150)
        self.editor.setMaximumHeight(260)
        self.root.addWidget(self.editor)
        row = QHBoxLayout()
        self.count = QLabel("0 / 20000")
        self.count.setObjectName("Small")
        row.addWidget(self.count)
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        send = QPushButton("发送")
        send.setObjectName("Primary")
        send.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(send)
        self.root.addLayout(row)
        self.editor.textChanged.connect(
            lambda: self.count.setText(f"{len(self.editor.toPlainText())} / 20000")
        )

    def text(self) -> str:
        return self.editor.toPlainText().strip()


class InputDialog(BaseDialog):
    def __init__(
        self,
        title: str,
        label: str,
        theme: str,
        *,
        placeholder: str = "",
        value: str = "",
        password: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, title, theme, 430)
        p = palette(theme)
        t = QLabel(label)
        t.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.root.addWidget(t)
        self.edit = QLineEdit(value)
        self.edit.setPlaceholderText(placeholder)
        if password:
            self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.root.addWidget(self.edit)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        self.root.addLayout(row)
        self.edit.returnPressed.connect(self.accept)

    def value(self) -> str:
        return self.edit.text().strip()


class QRDialog(BaseDialog):
    def __init__(self, node: Any, theme: str, parent: Optional[QWidget] = None):
        super().__init__(parent, "手机访问", theme, 470)
        p = palette(theme)
        self.node = node
        cfg = node.config
        title = QLabel("用手机扫码连接")
        title.setStyleSheet("font-size: 19px; font-weight: 700;")
        self.root.addWidget(title)

        preferred = cfg.prefer_https and bool(node.tls_material)
        url = node.pair_url()
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_label.setPixmap(self._make_qr(url, p["accent"]))
        self.root.addWidget(qr_label)

        code = cfg.web_pair_code if cfg.web_pairing else "已关闭"
        code_label = QLabel(f"配对码  {code}")
        code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_label.setStyleSheet(f"font-size: 24px; font-weight: 700; letter-spacing: 4px; color:{p['accent']};")
        self.root.addWidget(code_label)

        for label, value in (
            ("HTTP", node.web_url(https=False)),
            ("HTTPS", node.web_url(https=True) if node.tls_material else "不可用（证书未启动）"),
        ):
            row = QHBoxLayout()
            tag = QLabel(label)
            tag.setObjectName("Small")
            tag.setFixedWidth(44)
            val = QLabel(value)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setStyleSheet("font-size: 11.5px;")
            copy = QPushButton("复制")
            copy.setObjectName("Ghost")
            copy.setFixedSize(48, 28)
            copy.setStyleSheet("padding: 2px 4px; font-size: 11.5px;")
            copy.clicked.connect(lambda _=False, v=value: self._copy(v))
            row.addWidget(tag)
            row.addWidget(val, 1)
            row.addWidget(copy)
            self.root.addLayout(row)

        if node.tls_material:
            fp = QLabel(f"TLS 指纹 {node.tls_material.fingerprint[:32]}")
            fp.setObjectName("Small")
            fp.setWordWrap(True)
            self.root.addWidget(fp)

        buttons = QHBoxLayout()
        open_btn = QPushButton("打开浏览器")
        open_btn.setObjectName("Ghost")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        rotate = QPushButton("轮换配对码")
        rotate.setObjectName("Ghost")
        rotate.clicked.connect(self._rotate)
        close = QPushButton("完成")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        buttons.addWidget(open_btn)
        buttons.addWidget(rotate)
        buttons.addStretch(1)
        buttons.addWidget(close)
        self.root.addLayout(buttons)
        self._qr_label = qr_label
        self._code_label = code_label

    def _make_qr(self, data: str, color: str) -> QPixmap:
        try:
            import qrcode
            from PIL import Image

            qr = qrcode.QRCode(border=2, box_size=8)
            qr.add_data(data)
            qr.make(fit=True)
            image = qr.make_image(fill_color=color, back_color="white").convert("RGB")
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            pix = QPixmap()
            pix.loadFromData(buf.getvalue(), "PNG")
            return pix.scaled(260, 260, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pix = QPixmap(260, 260)
            pix.fill(Qt.GlobalColor.white)
            return pix

    def _copy(self, value: str) -> None:
        QApplication.clipboard().setText(value)

    def _rotate(self) -> None:
        code = self.node.rotate_pair_code()
        self._code_label.setText(f"配对码  {code}")
        if self.node.tls_material:
            self._qr_label.setPixmap(self._make_qr(self.node.pair_url(), palette(self.theme)["accent"]))
