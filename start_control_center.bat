@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo A Central e o bot ja estao ligados.
  exit /b 0
)
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtual nao encontrado. Crie o .venv e instale requirements.txt.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" control_center.py --start-bot
if errorlevel 1 pause
