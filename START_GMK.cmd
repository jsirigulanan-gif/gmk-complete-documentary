@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title GMK P.T. Operator - Build 041

if exist ".venv\Scripts\pythonw.exe" (
  start "GMK" ".venv\Scripts\pythonw.exe" -m gmk_operator
  exit /b 0
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m gmk_operator
  exit /b %ERRORLEVEL%
)

echo GMK has not been installed on this computer yet.
echo Run INSTALL_GMK.cmd once, then run START_GMK.cmd again.
pause
exit /b 2
