@echo off
chcp 65001 >nul
rem One-click build (single-file exe).
rem The app name contains Chinese + emoji, so it lives inside build.spec (UTF-8).
rem Do NOT put --name on the command line: cmd reads args as GBK and the emoji
rem would turn into garbage. This file is kept ASCII-only on purpose.
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
.venv\Scripts\pyinstaller.exe --noconfirm --clean build.spec
echo.
echo Build done. Single-file exe is in the dist folder.
pause
