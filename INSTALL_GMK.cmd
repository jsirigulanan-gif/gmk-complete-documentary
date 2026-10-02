@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title GMK Installer - Build 041

echo ============================================================
echo  GMK Documentary Maker - Windows Setup
echo ============================================================
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if %ERRORLEVEL%==0 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo [ERROR] Python 3.10+ was not found.
  echo Install Python from python.org and enable "Add Python to PATH", then run this file again.
  pause
  exit /b 2
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 2)"
if not %ERRORLEVEL%==0 (
  echo [ERROR] GMK requires Python 3.10 or newer.
  pause
  exit /b 2
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating local Python environment...
  %PYTHON_CMD% -m venv .venv
  if not %ERRORLEVEL%==0 goto :fail
) else (
  echo [1/3] Local Python environment already exists.
)

echo [2/3] Installing required Python packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if not %ERRORLEVEL%==0 goto :fail

echo [3/3] Checking runtime...
".venv\Scripts\python.exe" -m gmk_operator --system-check
set "CHECK=%ERRORLEVEL%"

echo.
if "%CHECK%"=="0" (
  echo Setup complete. GMK runs directly from this folder. Double-click START_GMK.cmd to open the program.
) else (
  echo Setup completed, but one dependency still needs attention.
  echo If ffprobe is missing, START_GMK.cmd can still open the GUI;
  echo use the System tab to select ffprobe.exe manually.
)
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup failed. Check the messages above.
pause
exit /b 1
