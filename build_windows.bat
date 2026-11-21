@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please run install_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller==6.16.0
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name MPs_Aging_Predictor --add-data "assets;assets" --collect-all lightgbm --collect-all sklearn --collect-all xgboost main.py
if errorlevel 1 goto failed
echo Build created in dist\MPs_Aging_Predictor. Test it on Windows before distribution.
pause
exit /b 0
:failed
pause
exit /b 1
