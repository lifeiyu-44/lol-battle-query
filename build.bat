@echo off
rem 一键打包：生成 dist\LOL战绩查询.exe（单文件，可直接分享）
cd /d "%~dp0"
set PYI_ARGS=--noconfirm --clean --onefile --windowed --name "LOL战绩查询" --add-data "app\ui;ui" --hidden-import webview.platforms.edgechromium --hidden-import psutil
if exist app\champions_cache.json set PYI_ARGS=%PYI_ARGS% --add-data "app\champions_cache.json;."
.venv\Scripts\pyinstaller.exe %PYI_ARGS% run.py
echo.
echo 打包完成：dist\LOL战绩查询.exe
pause
