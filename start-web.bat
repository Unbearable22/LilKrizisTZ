@echo off
setlocal EnableExtensions
pushd "%~dp0" >nul 2>nul
if errorlevel 1 goto inaccessible_folder
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 goto use_py312
py -3.13 -c "import sys" >nul 2>nul
if not errorlevel 1 goto use_py313
:use_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python scripts\run_web.py %*
goto finished
:use_py312
py -3.12 scripts\run_web.py %*
goto finished
:use_py313
py -3.13 scripts\run_web.py %*
goto finished
:missing_python
echo Install Python 3.12 from https://www.python.org/downloads/windows/
echo Enable "Add Python to PATH", then run this file again.
popd
pause
exit /b 1
:inaccessible_folder
echo Cannot open the project folder. Check network access and permissions.
echo You can also copy the project to C:\Projects\LilKrizisTZ and run it there.
pause
exit /b 1
:finished
set "WEB_EXIT=%errorlevel%"
popd
if "%WEB_EXIT%"=="0" exit /b 0
echo.
echo Web chat could not start. Read the error above.
pause
exit /b %WEB_EXIT%
