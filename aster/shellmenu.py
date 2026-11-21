"""Windows 资源管理器右键菜单注册。

使用 HKCU 的经典 shell verb（无需管理员）。Windows 11 默认收在
「显示更多选项」里；这是系统对旧式 verb 的展示方式。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MULTI_VALUE = "发送到 Aster"
MENU_KEY = "AsterSend"


def _invoker() -> tuple[str, str]:
    """返回 (命令字符串, 图标路径)。"""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        command = f'"{exe}" --enqueue "%1"'
        return command, str(exe)
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    runner = ROOT / "run_gui.py"
    icon = ROOT / "assets" / "aster.ico"
    launcher = pythonw if pythonw.exists() else python
    command = f'"{launcher}" "{runner}" --enqueue "%1"'
    return command, str(icon if icon.exists() else launcher)


def register() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "仅 Windows 支持资源管理器右键"
    try:
        import winreg
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
    command, icon = _invoker()
    entries = [
        r"Software\Classes\*\shell\AsterSend",
        r"Software\Classes\Directory\shell\AsterSend",
    ]
    try:
        for key_path in entries:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, MULTI_VALUE)
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon)
                winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, key_path + r"\command", 0, winreg.KEY_WRITE
            ) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
        return True, "已注册资源管理器右键菜单"
    except OSError as exc:
        return False, str(exc)


def unregister() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "仅 Windows 支持资源管理器右键"
    try:
        import winreg
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
    entries = [
        r"Software\Classes\*\shell\AsterSend",
        r"Software\Classes\Directory\shell\AsterSend",
    ]
    for key_path in entries:
        for path in (key_path + r"\command", key_path):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                return False, str(exc)
    return True, "已移除资源管理器右键菜单"


def is_registered() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\*\shell\AsterSend\command"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return bool(value)
    except OSError:
        return False
