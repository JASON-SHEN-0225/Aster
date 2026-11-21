"""Windows 单实例守卫。"""

from __future__ import annotations

import ctypes
import os


ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """持有命名互斥体；进程退出或 release 时释放。"""

    def __init__(self, name: str = "Local\\Aster2GUI"):
        self.handle = None
        self.already_running = False
        if os.name != "nt":
            return
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.handle = kernel32.CreateMutexW(None, False, name)
            self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
            if self.already_running and self.handle:
                kernel32.CloseHandle(self.handle)
                self.handle = None
        except Exception:
            self.handle = None
            self.already_running = False

    def release(self) -> None:
        if self.handle and os.name == "nt":
            try:
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None

    def __del__(self):
        self.release()
