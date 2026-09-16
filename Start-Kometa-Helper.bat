@echo off
setlocal

set "KOMETA_PYTHON=%USERPROFILE%\Documents\Kometa\.venv\Scripts\python.exe"
set "APP_DIR=%~dp0"

if not exist "%KOMETA_PYTHON%" (
  echo Kometa Python was not found:
  echo "%KOMETA_PYTHON%"
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
"%KOMETA_PYTHON%" "%APP_DIR%imdb_collection_ui.py"
pause
