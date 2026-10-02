@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_clashbot.ps1"
if errorlevel 1 (
  echo Nao foi possivel encerrar todos os componentes.
  pause
  exit /b 1
)
timeout /t 2 /nobreak >nul
