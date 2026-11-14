@echo off
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Lancer.ps1"
set "code=%ERRORLEVEL%"
if not "%code%"=="0" if not defined GC_BALANCER_NONINTERACTIVE pause
exit /b %code%
