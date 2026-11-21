"""Aster GUI 配色与 Qt 样式表。"""

from __future__ import annotations

import sys
from pathlib import Path

_ASSET_DIR = Path(
    getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent)
) / "assets"
_CHEVRON = (_ASSET_DIR / "chevron-down.svg").as_posix()

LIGHT = {
    "bg": "#F4F7FB",
    "bg_alt": "#EDF2F9",
    "card": "#FFFFFF",
    "card_alt": "#F8FAFD",
    "text": "#172033",
    "text2": "#4C5B70",
    "text3": "#7B8798",
    "border": "#E2E8F2",
    "border_strong": "#CBD6E5",
    "accent": "#2E7CF6",
    "accent_hover": "#1D6AE5",
    "accent_soft": "#E8F1FF",
    "mint": "#13B99F",
    "mint_soft": "#E3F8F3",
    "danger": "#E04460",
    "danger_soft": "#FDECEF",
    "success": "#0D9F6E",
    "shadow": "rgba(51, 65, 85, 0.16)",
}

DARK = {
    "bg": "#0F1522",
    "bg_alt": "#141C2B",
    "card": "#172030",
    "card_alt": "#1B2536",
    "text": "#E9EFF9",
    "text2": "#A8B6CA",
    "text3": "#74839A",
    "border": "#243248",
    "border_strong": "#33445D",
    "accent": "#4C9AFF",
    "accent_hover": "#6AAEFF",
    "accent_soft": "#182C47",
    "mint": "#38D6B8",
    "mint_soft": "#14352F",
    "danger": "#FF7A90",
    "danger_soft": "#3A1D27",
    "success": "#34D399",
    "shadow": "rgba(0, 0, 0, 0.45)",
}


def palette(theme: str) -> dict[str, str]:
    return DARK if theme == "dark" else LIGHT


def build_qss(theme: str) -> str:
    p = palette(theme)
    return f"""
    * {{
        font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    }}
    QMainWindow, QWidget#Root {{
        background: {p['bg']};
        color: {p['text']};
    }}
    QWidget#Content {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['bg']}, stop:0.58 {p['bg']}, stop:1 {p['bg_alt']});
    }}
    QWidget {{
        color: {p['text']};
        font-size: 14px;
    }}
    QStackedWidget, QStackedWidget > QWidget {{
        background: transparent;
    }}
    QScrollArea,
    QScrollArea > QWidget > QWidget,
    QScrollArea > QWidget#qt_scrollarea_viewport {{
        background: transparent;
    }}
    QFrame#Sidebar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {p['card']}, stop:1 {p['card_alt']});
        border-right: 1px solid {p['border']};
    }}
    QFrame#TopBar {{
        background: transparent;
    }}
    QLabel {{
        background: transparent;
    }}
    QLabel#BrandName {{
        font-size: 19px;
        font-weight: 700;
        color: {p['text']};
    }}
    QLabel#BrandSub {{
        font-size: 12.5px;
        color: {p['text3']};
        letter-spacing: 2px;
    }}
    QLabel#PageTitle {{
        font-size: 28px;
        font-weight: 700;
        color: {p['text']};
    }}
    QLabel#PageSub {{
        font-size: 13px;
        color: {p['text3']};
    }}
    QLabel#SectionTitle {{
        font-size: 15px;
        font-weight: 650;
        color: {p['text']};
    }}
    QLabel#Muted {{
        color: {p['text3']};
        font-size: 12.5px;
    }}
    QLabel#Small {{
        color: {p['text3']};
        font-size: 12.5px;
    }}
    QLabel#HeroTitle {{
        font-size: 32px;
        font-weight: 750;
        color: {p['text']};
    }}
    QLabel#GradientTitle {{
        font-family: "Noto Sans SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
        font-size: 34px;
        font-weight: 700;
        letter-spacing: 0.5px;
        background: transparent;
    }}
    QFrame#HeroCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['card']}, stop:0.62 {p['card']}, stop:1 {p['accent_soft']});
        border: 1px solid {p['border']};
        border-radius: 18px;
    }}
    QLabel#HeroLead {{
        font-size: 13px;
        color: {p['text3']};
    }}
    QPushButton {{
        border: 1px solid transparent;
        border-radius: 10px;
        padding: 9px 14px;
        background: transparent;
        color: {p['text2']};
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {p['bg_alt']};
        color: {p['text']};
    }}
    QPushButton:pressed {{
        background: {p['border']};
    }}
    QPushButton:focus {{
        outline: none;
    }}
    QPushButton#Primary {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['accent']}, stop:1 {p['mint']});
        color: #FFFFFF;
        padding: 11px 20px;
        font-weight: 650;
        border: 1px solid transparent;
        border-radius: 11px;
    }}
    QPushButton#Primary:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['accent_hover']}, stop:1 {p['mint']});
    }}
    QPushButton#Primary:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['accent_hover']}, stop:1 {p['mint']});
    }}
    QPushButton#Primary:disabled {{
        background: {p['border_strong']};
        color: {p['text3']};
        border-color: transparent;
    }}
    QPushButton#Ghost {{
        background: {p['card']};
        border: 1px solid {p['border']};
        color: {p['text2']};
    }}
    QPushButton#Ghost:hover, QPushButton#Ghost:focus {{
        border-color: {p['accent']};
        background: {p['accent_soft']};
        color: {p['accent']};
    }}
    QPushButton#Ghost:pressed {{
        background: {p['border']};
        border-color: {p['border_strong']};
    }}
    QPushButton#Soft {{
        background: {p['accent_soft']};
        border: 1px solid transparent;
        color: {p['accent']};
        font-weight: 650;
    }}
    QPushButton#Soft:hover, QPushButton#Soft:focus {{
        background: {p['accent_soft']};
        border-color: {p['accent']};
        color: {p['accent_hover']};
    }}
    QPushButton#Danger {{
        background: {p['danger_soft']};
        border: 1px solid transparent;
        color: {p['danger']};
        font-weight: 650;
    }}
    QPushButton#Danger:hover, QPushButton#Danger:focus {{
        border-color: {p['danger']};
        color: {p['danger']};
    }}
    QPushButton#NavButton {{
        text-align: left;
        padding: 10px 13px;
        border: 1px solid transparent;
        border-radius: 10px;
        color: {p['text2']};
        font-size: 13.5px;
        font-weight: 600;
    }}
    QPushButton#NavButton:hover {{
        background: {p['bg_alt']};
        color: {p['text']};
    }}
    QPushButton#NavButton:checked {{
        background: {p['accent_soft']};
        border-color: {p['accent']};
        color: {p['accent']};
        font-weight: 650;
    }}
    QFrame#SchemeSwitch {{
        background: {p['bg_alt']};
        border: 1px solid {p['border']};
        border-radius: 15px;
    }}
    QPushButton#SchemeOption {{
        min-height: 18px;
        padding: 2px 7px;
        border: 0;
        border-radius: 11px;
        background: transparent;
        color: {p['text3']};
        font-size: 11px;
        font-weight: 650;
    }}
    QPushButton#SchemeOption:hover {{
        background: {p['border']};
        color: {p['text2']};
    }}
    QPushButton#SchemeOption:checked {{
        background: {p['accent_soft']};
        color: {p['accent']};
    }}
    QFrame#Card, QFrame#DeviceCard, QFrame#TransferCard, QFrame#DropZone, QFrame#SettingCard {{
        background: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 16px;
    }}
    QFrame#DropZone {{
        border: 1.5px dashed {p['border_strong']};
        background: {p['card_alt']};
    }}
    QFrame#DropZone[dragging="true"] {{
        border-color: {p['accent']};
        background: {p['accent_soft']};
    }}
    QFrame#DeviceCard[selected="true"] {{
        border: 1.5px solid {p['accent']};
        background: {p['accent_soft']};
    }}
    QFrame#DeviceCard:hover {{
        border-color: {p['accent']};
    }}
    QLabel#Pill {{
        background: {p['mint_soft']};
        color: {p['mint']};
        border-radius: 11px;
        padding: 5px 12px;
        font-size: 13px;
        font-weight: 650;
    }}
    QLabel#PillMuted {{
        background: {p['bg_alt']};
        color: {p['text3']};
        border-radius: 11px;
        padding: 5px 12px;
        font-size: 13px;
    }}
    QLineEdit, QTextEdit, QComboBox, QSpinBox {{
        background: {p['card_alt']};
        border: 1px solid {p['border']};
        border-radius: 9px;
        padding: 8px 10px;
        color: {p['text']};
        selection-background-color: {p['accent']};
        selection-color: #FFFFFF;
    }}
    QLineEdit:hover, QTextEdit:hover, QSpinBox:hover {{
        border-color: {p['border_strong']};
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border-color: {p['accent']};
    }}
    QComboBox {{
        min-height: 22px;
        padding: 8px 38px 8px 12px;
        border-radius: 10px;
        background: {p['card_alt']};
        outline: 0;
    }}
    QComboBox:focus {{
        outline: 0;
        border-color: {p['accent']};
    }}
    QComboBox:hover {{
        border-color: {p['border_strong']};
        background: {p['card']};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 34px;
        border: 0;
        border-left: 1px solid {p['border']};
        border-top-right-radius: 10px;
        border-bottom-right-radius: 10px;
        background: transparent;
    }}
    QComboBox::drop-down:hover {{
        background: {p['accent_soft']};
        border-left-color: {p['accent']};
    }}
    QComboBox::down-arrow {{
        image: url("{_CHEVRON}");
        width: 12px;
        height: 12px;
    }}
    QComboBoxPrivateContainer {{
        background: transparent;
        border: 0;
    }}
    QComboBoxPrivateContainer QFrame {{
        border: 0;
        background: {p['card']};
    }}
    QListView {{
        background: {p['card']};
        border: 0;
        border-radius: 9px;
        padding: 5px;
        outline: 0;
        selection-background-color: {p['accent_soft']};
        selection-color: {p['accent']};
    }}
    QListView::item {{
        min-height: 30px;
        padding: 6px 10px;
        border-radius: 6px;
        color: {p['text2']};
    }}
    QListView::item:hover {{
        background: {p['bg_alt']};
        color: {p['text']};
    }}
    QListView::item:selected {{
        background: {p['accent_soft']};
        color: {p['accent']};
    }}
    QComboBox QAbstractItemView {{
        background: {p['card']};
        border: 0;
        border-radius: 9px;
        padding: 5px;
        outline: 0;
        selection-background-color: {p['accent_soft']};
        selection-color: {p['accent']};
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 30px;
        padding: 6px 10px;
        border-radius: 6px;
        color: {p['text2']};
    }}
    QComboBox QAbstractItemView::item:hover {{
        background: {p['bg_alt']};
        color: {p['text']};
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {p['accent_soft']};
        color: {p['accent']};
    }}
    QPushButton#Switch {{
        background: {p['border']};
        border-radius: 12px;
        min-width: 42px;
        max-width: 42px;
        min-height: 24px;
        max-height: 24px;
        padding: 0;
    }}
    QPushButton#Switch:checked {{
        background: {p['accent']};
    }}
    QProgressBar {{
        border: 0;
        border-radius: 4px;
        background: {p['bg_alt']};
        min-height: 7px;
        max-height: 7px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        border-radius: 4px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['accent']}, stop:1 {p['mint']});
    }}
    QScrollArea {{
        border: 0;
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p['border_strong']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p['text3']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
        height: 0;
    }}
    QScrollBar:horizontal {{
        height: 0;
    }}
    QTableWidget {{
        background: {p['card']};
        alternate-background-color: {p['card_alt']};
        border: 1px solid {p['border']};
        border-radius: 12px;
        gridline-color: {p['border']};
        selection-background-color: {p['accent_soft']};
        selection-color: {p['text']};
    }}
    QHeaderView::section {{
        background: {p['card_alt']};
        color: {p['text3']};
        border: 0;
        border-bottom: 1px solid {p['border']};
        padding: 7px;
        font-size: 12.5px;
        font-weight: 650;
    }}
    QMenu {{
        background: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 9px;
        padding: 5px;
    }}
    QMenu::item {{
        padding: 7px 20px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {p['accent_soft']};
        color: {p['text']};
    }}
    QToolTip {{
        background: {p['text']};
        color: {p['bg']};
        border: 0;
        padding: 5px 8px;
        border-radius: 5px;
    }}
    QDialog {{
        background: {p['bg']};
        color: {p['text']};
    }}
    QMessageBox {{
        background: {p['bg']};
    }}
    QLabel#Toast {{
        background: {p['text']};
        color: {p['bg']};
        border-radius: 9px;
        padding: 8px 14px;
        font-size: 12.5px;
    }}
    QSplitter::handle {{
        background: {p['border']};
    }}
    QCheckBox {{
        color: {p['text2']};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {p['border_strong']};
        border-radius: 4px;
        background: {p['card_alt']};
    }}
    QCheckBox::indicator:checked {{
        background: {p['accent']};
        border-color: {p['accent']};
    }}
    """
