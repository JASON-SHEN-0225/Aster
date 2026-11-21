"""PyInstaller GUI 入口（Aster.exe）。"""

import multiprocessing

from aster.gui.app import run_gui

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(run_gui())
