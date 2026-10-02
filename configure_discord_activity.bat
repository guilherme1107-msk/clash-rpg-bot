@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" configure_discord_activity.py
pause
