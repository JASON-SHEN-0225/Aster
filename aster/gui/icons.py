"""Qt 线性图标（本地 SVG 渲染，无外部资源）。"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..util import resource_path

_SVGS = {
    "star": '<path d="M12 2.4c.8 5.9 3.7 8.8 9.6 9.6-5.9.8-8.8 3.7-9.6 9.6-.8-5.9-3.7-8.8-9.6-9.6 5.9-.8 8.8-3.7 9.6-9.6Z" fill="{color}" stroke="none"/>',
    "upload": '<path d="M12 16V4.5m0 0 4.2 4.2M12 4.5 7.8 8.7M4.5 15.8v2.2A2 2 0 0 0 6.5 20h11a2 2 0 0 0 2-2v-2.2"/>',
    "download": '<path d="M12 4v11.5m0 0 4.2-4.2M12 15.5l-4.2-4.2M4.5 15.8v2.2A2 2 0 0 0 6.5 20h11a2 2 0 0 0 2-2v-2.2"/>',
    "folder": '<path d="M3.4 7.7A2.2 2.2 0 0 1 5.6 5.5h3.2c.6 0 1.1.2 1.6.6l1.4 1.3c.4.4.9.6 1.5.6h5.1a2.2 2.2 0 0 1 2.2 2.2v6.5a2.2 2.2 0 0 1-2.2 2.2H5.6a2.2 2.2 0 0 1-2.2-2.2V7.7Z"/>',
    "text": '<rect x="4" y="4" width="16" height="16" rx="3.2"/><path d="M8 8.5h8M8 12h8M8 15.5h4.8"/>',
    "history": '<path d="M4.2 12a7.8 7.8 0 1 0 2.1-5.3M4.2 5v3.8h3.8"/><path d="M12 7.5V12l3 1.8"/>',
    "settings": '<path d="M4.2 7.2h8.9M17.8 7.2h2M4.2 12h4.2M12.2 12h7.6M4.2 16.8h10M18.8 16.8h1"/>' '<circle cx="15.5" cy="7.2" r="2"/><circle cx="10.3" cy="12" r="2"/><circle cx="16.8" cy="16.8" r="2"/>',
    "monitor": '<rect x="3.4" y="4.6" width="17.2" height="11.6" rx="2.2"/><path d="M9.2 19.5h5.6M12 16.2v3.3"/>',
    "phone": '<rect x="6.6" y="3" width="10.8" height="18" rx="2.6"/><path d="M10.5 5.4h3M10.9 18.4h2.2"/>',
    "check": '<path d="m5 12.4 4.5 4.4L19 6.9"/>',
    "close": '<path d="M6.2 6.2 17.8 17.8M17.8 6.2 6.2 17.8"/>',
    "copy": '<rect x="8.8" y="8.8" width="10.6" height="10.6" rx="2.4"/><path d="M6.9 15.1H5.8a1.9 1.9 0 0 1-1.9-1.9V5.9A1.9 1.9 0 0 1 5.8 4h7.3a1.9 1.9 0 0 1 1.9 1.9v1.1"/>',
    "qr": '<rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><path d="M14 14h2.5v2.5H14zM19 14h1v1M14 19h2M18 18h2v2h-2z"/>',
    "link": '<path d="m9.7 14.3 4.6-4.6M7.6 17.8l-1.2 1.2a3.7 3.7 0 0 1-5.2-5.2l3.2-3.2a3.7 3.7 0 0 1 5.2 0"/>' '<path d="m16.4 6.2 1.2-1.2a3.7 3.7 0 0 1 5.2 5.2l-3.2 3.2a3.7 3.7 0 0 1-5.2 0"/>',
    "send": '<path d="M21 3.2 3.5 9.9l6.9 3.4 3.4 6.9L21 3.2Z"/><path d="m10.4 13.3 4.4-4.4"/>',
    "alert": '<path d="M12 3.4 21 19.6H3L12 3.4Z"/><path d="M12 9.3v4.3"/><circle cx="12" cy="16.5" r=".9" fill="{color}" stroke="none"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.8v2M12 19.2v2M2.8 12h2M19.2 12h2M5.4 5.4l1.4 1.4M17.2 17.2l1.4 1.4M18.6 5.4l-1.4 1.4M6.8 17.2l-1.4 1.4"/>',
    "moon": '<path d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.2 8.2 0 1 0 10.2 10.2Z"/>',
    "refresh": '<path d="M20 11.6a8 8 0 1 0-2 5.6M20 4.6v6.3h-6.3"/>',
    "wifi": '<path d="M3.4 8.9a13 13 0 0 1 17.2 0M6.8 12.4a8.2 8.2 0 0 1 10.4 0M10 15.9a3.5 3.5 0 0 1 4 0"/><circle cx="12" cy="19.2" r="1.1" fill="{color}" stroke="none"/>',
    "shield": '<path d="M12 3.2 19.2 6v5.6c0 4.3-3 7.4-7.2 9.2-4.2-1.8-7.2-4.9-7.2-9.2V6L12 3.2Z"/><path d="m9 11.8 2 2 4.2-4.4"/>',
    "clock": '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.4v5l3.2 1.8"/>',
    "linkoff": '<path d="m4 4 16 16M9.7 14.3l4.6-4.6M7.6 17.8l-1.2 1.2a3.7 3.7 0 0 1-5.2-5.2l3.2-3.2a3.7 3.7 0 0 1 5.2 0"/>',
}


@lru_cache(maxsize=256)
def make_icon(name: str, color: str = "#4C5B70", size: int = 20) -> QIcon:
    if name not in _SVGS:
        name = "star"
    body = _SVGS[name].replace("{color}", color)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="' + color + '" stroke-width="1.65" '
        'stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


def app_icon() -> QIcon:
    for path in (resource_path("assets", "aster.ico"), resource_path("assets", "aster-512.png")):
        try:
            if path.exists():
                return QIcon(str(path))
        except Exception:
            pass
    return make_icon("star", "#2E7CF6", 32)
