@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m notice_tap check
