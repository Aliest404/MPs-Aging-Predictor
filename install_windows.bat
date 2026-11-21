@echo off
setlocal
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 was not found. Install Python 3.12 with Tkinter and the Python Launcher.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" main.py --verify
if errorlevel 1 goto failed
echo Installation and available-model checks completed.
echo Next: double-click run_windows.bat
pause
exit /b 0
:failed
echo Installation or model verification failed. Read the error above.
pause
exit /b 1
