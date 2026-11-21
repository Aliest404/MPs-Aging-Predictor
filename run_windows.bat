@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run install_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
  echo The application could not start. Please copy the error above for troubleshooting.
  pause
  exit /b 1
)
