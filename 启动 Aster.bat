@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0Aster.exe" (
    start "" "%~dp0Aster.exe" %*
) else (
    start "" pythonw "%~dp0run_gui.py" %*
)
