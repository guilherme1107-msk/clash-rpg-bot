@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtual nao encontrado. Crie o .venv e instale requirements.txt.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" control_center.py
if errorlevel 1 pause
