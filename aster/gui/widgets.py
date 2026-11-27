"""Aster GUI 自绘/组合控件。"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .icons import make_icon
from .theme import palette
from ..util import human_size, human_speed, format_duration


class SchemeSwitch(QFrame):
    """首页左上角的 HTTP / HTTPS 分段开关。"""

    changed = Signal(bool)

    def __init__(self, theme: str = "light", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("SchemeSwitch")
        self.setFixedHeight(30)
        self.setMinimumWidth(106)
        self.setMaximumWidth(118)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)
        self.http_btn = QPushButton("HTTP")
        self.http_btn.setObjectName("SchemeOption")
        self.http_btn.setCheckable(True)
        self.http_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.https_btn = QPushButton("HTTPS")
        self.https_btn.setObjectName("SchemeOption")
        self.https_btn.setCheckable(True)
        self.https_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.http_btn)
        row.addWidget(self.https_btn)
        self.http_btn.clicked.connect(lambda: self._choose(False))
        self.https_btn.clicked.connect(lambda: self._choose(True))
        self.set_prefer(False)

    def set_prefer(self, prefer: bool) -> None:
        prefer = bool(prefer)
        self.http_btn.setChecked(not prefer)
        self.https_btn.setChecked(prefer)
        self.http_btn.setEnabled(True)
        self.https_btn.setEnabled(True)

    def _choose(self, prefer: bool) -> None:
        self.set_prefer(prefer)
        self.changed.emit(prefer)


class ThemeSwitch(QFrame):
    """顶栏右上角的浅色 / 深色滑块。"""

    changed = Signal(bool)

    def __init__(self, theme: str = "light", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ThemeSwitch")
        self.setFixedSize(64, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("切换浅色 / 深色")
        self._dark = theme == "dark"
        self._knob = 1.0 if self._dark else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._icons: dict[tuple[str, str], QPixmap] = {}

    def _icon(self, name: str, color: str, size: int) -> QPixmap:
        key = (name, color)
        pixmap = self._icons.get(key)
        if pixmap is None:
            pixmap = make_icon(name, color, size).pixmap(size, size)
            self._icons[key] = pixmap
        return pixmap

    def _get_knob(self) -> float:
        return self._knob

    def _set_knob(self, value: float) -> None:
        self._knob = float(value)
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def is_dark(self) -> bool:
        return self._dark

    def set_dark(self, dark: bool, animate: bool = True) -> None:
        dark = bool(dark)
        if dark == self._dark and abs(self._knob - (1.0 if dark else 0.0)) < 0.01:
            return
        self._dark = dark
        target = 1.0 if dark else 0.0
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._knob)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_knob(target)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.set_dark(not self._dark)
            self.changed.emit(self._dark)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = palette("dark" if self._dark else "light")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.8, 0.8, self.width() - 1.6, self.height() - 1.6)
        track = QColor(p["accent"] if self._dark else p["bg_alt"])
        if self._dark:
            track.setAlpha(215)
        painter.setPen(QPen(QColor(p["border_strong"] if not self._dark else p["accent"]), 1))
        painter.setBrush(track)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        knob = 24.0
        travel = self.width() - knob - 6.0
        x = 3.0 + travel * self._knob
        painter.setPen(Qt.PenStyle.NoPen)
        shadow = QColor(10, 20, 40, 32)
        painter.setBrush(shadow)
        painter.drawEllipse(QPointF(x + knob / 2, 2.4 + knob / 2), knob / 2, knob / 2)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QPointF(x + knob / 2, 2.2 + knob / 2), knob / 2, knob / 2)

        sun_active = not self._dark
        moon_active = self._dark
        sun_icon = self._icon("sun", p["accent"] if sun_active else p["text3"], 15)
        moon_icon = self._icon("moon", p["accent"] if moon_active else p["text3"], 14)
        painter.drawPixmap(int(9), int((self.height() - 15) / 2), sun_icon)
        painter.drawPixmap(int(self.width() - 9 - 14), int((self.height() - 14) / 2), moon_icon)
        painter.end()


class GradientTitle(QLabel):
    """蓝→薄荷渐变的大标题（带缓慢流动效果）。"""

    def __init__(self, text: str, theme: str = "light", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._theme = theme
        self._phase = 0.0
        self.setObjectName("GradientTitle")
        font = QFont("Noto Sans SC")
        font.setPixelSize(34)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.3)
        self.setFont(font)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def _advance(self) -> None:
        self._phase = (self._phase + 0.006) % 1.0
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.setFixedHeight(self.fontMetrics().height() + 2)

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def sizeHint(self) -> QSize:
        metrics = self.fontMetrics()
        return QSize(metrics.horizontalAdvance(self.text()) + 4, metrics.height() + 2)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = palette(self._theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self.font())
        rect = self.rect()
        text_width = max(1, self.fontMetrics().horizontalAdvance(self.text()))
        grad = QLinearGradient(rect.left(), rect.center().y(), rect.left() + text_width, rect.center().y())
        grad.setColorAt(0.0, QColor(p["accent"]))
        grad.setColorAt(1.0, QColor(p["accent"]))
        # 薄荷高光在文字上缓慢来回流动，形成持续的渐变呼吸感
        highlight = 0.5 + 0.42 * math.sin(self._phase * math.tau)
        grad.setColorAt(max(0.02, min(0.98, highlight)), QColor(p["mint"]))
        grad.setColorAt(max(0.04, min(0.99, highlight + 0.1)), QColor(p["accent"]))
        fm = self.fontMetrics()
        baseline = rect.bottom() - fm.descent() - 1
        path = QPainterPath()
        path.addText(float(rect.left()), float(baseline), self.font(), self.text())
        painter.fillPath(path, QBrush(grad))
        painter.end()


class HeroLogo(QWidget):
    """首页星轨动画：旋转轨道 + 呼吸星芒。"""

    def __init__(self, theme: str = "light", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(132, 132)
        self._angle = 0.0
        self._pulse = 0.0
        self._theme = theme
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def _tick(self) -> None:
        self._angle = (self._angle + 0.55) % 360
        self._pulse += 0.045
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = palette(self._theme)
        accent = QColor(p["accent"])
        mint = QColor(p["mint"])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = self.width() / 2, self.height() / 2
        breathe = (math.sin(self._pulse) + 1) / 2

        # 光晕
        glow = QColor(accent)
        glow.setAlpha(18 + int(18 * breathe))
        for radius, alpha in ((52, 10), (38, 14), (26, 18)):
            c = QColor(glow)
            c.setAlpha(alpha + int(10 * breathe))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # 两条轨道
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), 105), 1.15)
        painter.setPen(pen)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle)
        painter.scale(1.0, 0.40)
        painter.drawEllipse(QPointF(0, 0), 54, 54)
        painter.restore()

        pen = QPen(QColor(mint.red(), mint.green(), mint.blue(), 115), 1.05)
        painter.setPen(pen)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._angle * 1.35 + 24)
        painter.scale(1.0, 0.50)
        painter.drawEllipse(QPointF(0, 0), 40, 40)
        painter.restore()

        # 轨道上的小点
        rad = math.radians(self._angle)
        ox = cx + math.cos(rad) * 54
        oy = cy + math.sin(rad) * 54 * 0.40
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(mint)
        painter.drawEllipse(QPointF(ox, oy), 3.0, 3.0)

        # 四角星
        scale = 1.0 + 0.035 * breathe
        star = QPainterPath()
        for i in range(8):
            angle = -math.pi / 2 + i * math.pi / 4
            radius = (26 if i % 2 == 0 else 7.5) * scale
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            if i == 0:
                star.moveTo(x, y)
            else:
                star.lineTo(x, y)
        star.closeSubpath()
        gradient = QLinearGradient(cx - 24, cy - 24, cx + 24, cy + 24)
        gradient.setColorAt(0.0, accent)
        gradient.setColorAt(1.0, mint)
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(star)

        # 中心点缀
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QPointF(cx, cy), 2.6, 2.6)


class Toast(QLabel):
    """浮在主窗口底部的轻提示。单个实例复用，避免 Qt 对象销毁后回调。"""

    def __init__(self, parent: QWidget, message: str, kind: str = "info"):
        super().__init__(message, parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMaximumWidth(460)
        self.adjustSize()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._anim_finished)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self.show_message(message)

    def show_message(self, message: str) -> None:
        self.setText(message)
        self.adjustSize()
        self._hide_timer.stop()
        self._anim.stop()
        self._effect.setOpacity(0.0)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(180)
        self._anim.start()
        self._hide_timer.start(2600)

    def _fade_out(self) -> None:
        self._hide_timer.stop()
        if not self.isVisible():
            return
        self._anim.stop()
        self._anim.setDuration(260)
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _anim_finished(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 26
        self.move(max(10, x), max(10, y))


class DropZone(QFrame):
    filesDropped = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(make_icon("upload", "#2E7CF6", 26).pixmap(26, 26))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("拖拽文件或文件夹到这里")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 14px; font-weight: 650;")
        sub = QLabel("")
        sub.setObjectName("Muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.hide()
        layout.addWidget(self.icon_label)
        layout.addWidget(title)
        layout.addWidget(sub)

    def _set_drag(self, value: bool) -> None:
        self.setProperty("dragging", value)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_drag(False)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_drag(False)
        paths = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local and os.path.exists(local):
                paths.append(local)
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.filesDropped.emit([])
        super().mousePressEvent(event)


class DeviceCard(QFrame):
    clicked = Signal(dict)

    def __init__(self, peer: dict[str, Any], theme: str = "light", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DeviceCard")
        self.peer = peer
        self.theme = theme
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(270)
        self.setMaximumWidth(330)
        self.setMinimumHeight(98)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._selected = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(11)

        self.avatar = QLabel()
        self.avatar.setFixedSize(44, 44)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.name = QLabel()
        self.name.setStyleSheet("font-size: 14.5px; font-weight: 650;")
        self.name.setMaximumWidth(205)
        self.name.setWordWrap(False)
        self.addr = QLabel()
        self.addr.setObjectName("Muted")
        self.addr.setMaximumWidth(235)
        self.addr.setWordWrap(False)
        self.type_label = QLabel()
        self.type_label.setObjectName("Muted")
        self.type_label.setStyleSheet("font-size: 12px;")
        info.addWidget(self.name)
        info.addWidget(self.addr)
        info.addWidget(self.type_label)
        layout.addLayout(info, 1)

        self.status = QLabel()
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setFixedHeight(26)
        layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignTop)
        self.update_peer(peer, theme)

    def update_peer(self, peer: dict[str, Any], theme: str) -> None:
        self.peer = peer
        self.theme = theme
        online = bool(peer.get("online", True))
        is_web = str(peer.get("device_type") or "") == "web"
        name = str(peer.get("alias") or peer.get("name") or "未知设备")
        self.name.setText(name)
        self.name.setToolTip(name)
        client = str(peer.get("client") or "web").lower()
        if is_web:
            if client == "apk":
                addr = f"APK 手机 · {peer.get('ip') or '局域网'}"
                self.type_label.setText("Android 手机")
            else:
                addr = f"网页端 · {peer.get('ip') or '局域网'}"
                self.type_label.setText("网页端设备")
            icon_id = "phone"
        else:
            addr = f"{peer.get('ip') or '—'}:{peer.get('port') or '—'}"
            platform = str(peer.get("platform") or "").strip()
            self.type_label.setText(platform or "电脑")
            icon_id = "monitor"
        self.addr.setText(addr)
        p = palette(theme)
        icon_color = p["accent"] if online else p["text3"]
        self.avatar.setPixmap(make_icon(icon_id, icon_color, 24).pixmap(24, 24))
        self.avatar.setStyleSheet(
            f"background: {p['accent_soft'] if online else p['bg_alt']}; border-radius: 12px;"
        )
        self.status.setText("在线" if online else "离线")
        self.status.setStyleSheet(
            f"background:{p['mint_soft'] if online else p['bg_alt']}; color:{p['mint'] if online else p['text3']};"
            "border-radius:11px; padding:2px 10px; font-size:14px; font-weight:650;"
        )
        self.set_selected(self._selected)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.peer)
        super().mousePressEvent(event)


class TransferCard(QFrame):
    cancelClicked = Signal(str)

    def __init__(self, transfer: dict[str, Any], theme: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("TransferCard")
        self.transfer = transfer
        self.theme = theme
        self.setMinimumHeight(86)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFixedSize(34, 34)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self.icon)
        heading = QVBoxLayout()
        heading.setSpacing(1)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 14px; font-weight: 650;")
        self.sub = QLabel()
        self.sub.setObjectName("Muted")
        heading.addWidget(self.title)
        heading.addWidget(self.sub)
        top.addLayout(heading, 1)
        self.status = QLabel()
        self.status.setObjectName("PillMuted")
        top.addWidget(self.status)
        self.cancel = QPushButton("取消")
        self.cancel.setObjectName("Ghost")
        self.cancel.setFixedHeight(28)
        self.cancel.setStyleSheet("padding: 3px 9px; font-size: 11px;")
        self.cancel.clicked.connect(lambda: self.cancelClicked.emit(str(self.transfer.get("id") or "")))
        self.cancel.hide()
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(8)
        self.stats = QLabel()
        self.stats.setObjectName("Small")
        foot.addWidget(self.stats, 1)
        foot.addWidget(self.cancel)
        layout.addLayout(foot)
        self.update_transfer(transfer, theme)

    def update_transfer(self, transfer: dict[str, Any], theme: str) -> None:
        if theme != self.theme:
            self.theme = theme
        self.transfer = transfer
        p = palette(theme)
        status = str(transfer.get("status") or "active")
        direction = str(transfer.get("direction") or "out")
        files = transfer.get("files") or []
        total = int(transfer.get("total_bytes") or 0)
        done = int(transfer.get("done_bytes") or 0)
        pct = (done / total * 100) if total else (100 if status == "completed" else 0)
        is_in = direction == "in"
        peer = (transfer.get("peer") or {}).get("alias") or "电脑"
        if files:
            title = files[0].get("name") or "文件"
            if len(files) > 1:
                title = f"{title} 等 {len(files)} 个文件"
        else:
            title = "文本"
        self.title.setText(("接收自 " if is_in else "发送到 ") + str(peer))
        self.sub.setText(title)
        self.title.setToolTip(title)
        self.icon.setPixmap(
            make_icon("download" if is_in else "upload", p["accent"], 19).pixmap(19, 19)
        )
        self.icon.setStyleSheet(f"background:{p['accent_soft']}; border-radius:9px;")
        labels = {
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
        self.status.setText(labels.get(status, status))
        if status == "completed":
            self.status.setStyleSheet(
                f"background:{p['mint_soft']}; color:{p['mint']}; border-radius:11px; padding:2px 10px; font-size:14px; font-weight:650;"
            )
        elif status in ("failed", "rejected"):
            self.status.setStyleSheet(
                f"background:{p['danger_soft']}; color:{p['danger']}; border-radius:11px; padding:2px 10px; font-size:14px; font-weight:650;"
            )
        elif status in ("waiting", "pending"):
            self.status.setStyleSheet(
                f"background:{p['bg_alt']}; color:{p['text3']}; border-radius:11px; padding:2px 10px; font-size:14px; font-weight:650;"
            )
        else:
            self.status.setStyleSheet(
                f"background:{p['accent_soft']}; color:{p['accent']}; border-radius:11px; padding:2px 10px; font-size:14px; font-weight:650;"
            )
        self.progress.setValue(int(max(0, min(1000, pct * 10))))
        speed = float(transfer.get("speed") or 0)
        avg_speed = float(transfer.get("avg_speed") or speed)
        eta = transfer.get("eta")
        if status == "completed":
            stats = f"完成 · {human_size(total)}"
            if avg_speed > 0:
                stats += f"  ·  {human_speed(avg_speed)}"
        elif status in ("failed", "rejected"):
            stats = str(transfer.get("error") or "传输失败")
        elif status in ("waiting", "pending"):
            stats = "等待对方确认…"
        elif status == "verifying":
            stats = "正在校验完整性…"
        else:
            stats = f"{human_size(done)} / {human_size(total)}"
            if speed > 0:
                stats += f"  ·  {human_speed(speed)}"
            if eta:
                stats += f"  ·  剩余 {format_duration(eta)}"
        self.stats.setText(stats)
        self.cancel.setVisible(
            status in ("waiting", "pending", "active", "uploading", "verifying")
        )


class FileRow(QFrame):
    removeClicked = Signal(str)

    def __init__(self, path: str, size: int, theme: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.path = path
        self.setMinimumHeight(42)
        p = palette(theme)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(9)
        icon = QLabel()
        icon.setPixmap(make_icon("folder" if Path(path).is_dir() else "text", p["text3"], 16).pixmap(16, 16))
        layout.addWidget(icon)
        labels = QVBoxLayout()
        labels.setSpacing(0)
        name = QLabel(Path(path).name or path)
        name.setStyleSheet("font-size: 12.5px; font-weight: 550;")
        name.setToolTip(path)
        meta = QLabel(human_size(size) if size else "文件夹")
        meta.setObjectName("Small")
        labels.addWidget(name)
        labels.addWidget(meta)
        layout.addLayout(labels, 1)
        btn = QPushButton()
        btn.setObjectName("Ghost")
        btn.setFixedSize(26, 26)
        btn.setIcon(make_icon("close", p["text3"], 13))
        btn.setStyleSheet("padding:0;")
        btn.clicked.connect(lambda: self.removeClicked.emit(path))
        layout.addWidget(btn)
        self.setStyleSheet(f"QFrame {{ border-bottom: 1px solid {p['border']}; }}")


class EmptyHint(QWidget):
    def __init__(self, icon_id: str, title: str, sub: str, theme: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        p = palette(theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 34, 20, 34)
        layout.setSpacing(7)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel()
        icon.setPixmap(make_icon(icon_id, p["text3"], 30).pixmap(30, 30))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet("font-size: 14px; font-weight: 600;")
        s = QLabel(sub)
        s.setObjectName("Muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        layout.addWidget(t)
        layout.addWidget(s)
