@echo off
setlocal

set "APP_DIR=%~dp0"
set "KOMETA_PYTHON=%USERPROFILE%\Documents\Kometa\.venv\Scripts\python.exe"
set "APP_EXE_DIR=%APP_DIR%dist\Kometa Helper"

if not exist "%KOMETA_PYTHON%" (
  echo Kometa Python was not found:
  echo "%KOMETA_PYTHON%"
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
"%KOMETA_PYTHON%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
  "%KOMETA_PYTHON%" -m pip install pyinstaller
  if errorlevel 1 exit /b 1
)

"%KOMETA_PYTHON%" -m pip show pywebview >nul 2>&1
if errorlevel 1 (
  "%KOMETA_PYTHON%" -m pip install -r "%APP_DIR%requirements.txt"
  if errorlevel 1 exit /b 1
)

"%KOMETA_PYTHON%" -m PyInstaller --noconfirm --clean --windowed --onedir --name "Kometa Helper" ^
  --distpath "%APP_DIR%dist" ^
  --workpath "%APP_DIR%build" ^
  --add-data "%APP_DIR%refresh-plex-movie-show-libraries.ps1;." ^
  --add-data "%APP_DIR%Run-Kometa-Helper-Refresh-All-Posters.bat;." ^
  --hidden-import tkinter ^
  --hidden-import tkinter.filedialog ^
  --collect-all webview ^
  --collect-all clr_loader ^
  --collect-all pythonnet ^
  "%APP_DIR%imdb_collection_ui.py"
if errorlevel 1 (
  pause
  exit /b 1
)

copy /Y "%APP_DIR%refresh-plex-movie-show-libraries.ps1" "%APP_EXE_DIR%\refresh-plex-movie-show-libraries.ps1" >nul
copy /Y "%APP_DIR%Run-Kometa-Helper-Refresh-All-Posters.bat" "%APP_EXE_DIR%\Run-Kometa-Helper-Refresh-All-Posters.bat" >nul

echo.
echo Built Kometa Helper app:
echo "%APP_EXE_DIR%\Kometa Helper.exe"
pause
