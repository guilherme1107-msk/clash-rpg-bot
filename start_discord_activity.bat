@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort 8780 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo A Activity ja esta ligada.
  exit /b 0
)
if not exist "ui\discord-activity\node_modules" (
  pushd "ui\discord-activity"
  call npm install
  popd
)
pushd "ui\discord-activity"
call npm run build
if errorlevel 1 exit /b 1
popd
".venv\Scripts\python.exe" activity_server.py
