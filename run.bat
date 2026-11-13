@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: creating environment and installing packages...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 ( echo Python not found. Install Python 3.10+ from python.org first. & pause & exit /b 1 )
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 ( echo Package install failed. & pause & exit /b 1 )
)
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 pause
