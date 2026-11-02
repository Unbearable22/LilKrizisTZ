@echo off
setlocal EnableExtensions
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1" %*
set "WEB_EXIT=%errorlevel%"
if "%WEB_EXIT%"=="0" exit /b 0
echo.
echo Web chat could not start. Read the error above.
pause
exit /b %WEB_EXIT%
