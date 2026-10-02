@echo off
setlocal
cd /d "%~dp0"
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
"%CSC%" /nologo /target:winexe /out:ClashBot.exe /r:System.Windows.Forms.dll /r:System.Drawing.dll /resource:assets\clashbot-launcher-bg.png,ClashBotBackdrop ClashBotLauncher.cs
if errorlevel 1 pause
