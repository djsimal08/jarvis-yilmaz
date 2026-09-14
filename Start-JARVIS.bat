@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "JARVIS.exe" (
  start "" "JARVIS.exe"
  exit /b 0
)
if not exist ".venv\Scripts\pythonw.exe" (
  echo JARVIS kurulmamış. Önce KURULUM.bat dosyasını çalıştırın.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m agent.launcher
