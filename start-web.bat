@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
if not exist "%~dp0scripts\bootstrap_windows.ps1" (
    echo Startup scripts are missing. Extract the complete project archive first.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_windows.ps1" %*
set "WEB_EXIT=%errorlevel%"
if "%WEB_EXIT%"=="0" exit /b 0
echo.
echo Web chat could not start. Read the error above.
pause
exit /b %WEB_EXIT%
