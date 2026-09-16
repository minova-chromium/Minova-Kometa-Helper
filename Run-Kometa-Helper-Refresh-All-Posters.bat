@echo off
setlocal

set "APP_DIR=%~dp0"
set "OUTPUTS_DIR=%APP_DIR%.."
set "HELPER_DATA_DIR=%USERPROFILE%\Documents\Kometa-Helper\runtime"
set "QUICKSTART_CONFIG=%USERPROFILE%\Documents\Kometa-Quickstart\config\jolly_goodall_config.yml"
set "KOMETA_DIR=%USERPROFILE%\Documents\Kometa"
set "PYTHON_EXE=%KOMETA_DIR%\.venv\Scripts\python.exe"
set "KOMETA_SCRIPT=%KOMETA_DIR%\kometa.py"
set "KOMETA_RUN_CONFIG=%KOMETA_DIR%\config\quickstart-run-config.yml"
set "PLEX_REFRESH_SCRIPT=%APP_DIR%refresh-plex-movie-show-libraries.ps1"
if not exist "%PLEX_REFRESH_SCRIPT%" set "PLEX_REFRESH_SCRIPT=%OUTPUTS_DIR%\refresh-plex-movie-show-libraries.ps1"
set "LOCATIONS_JSON=%HELPER_DATA_DIR%\library-locations.json"
set "LOG_FILE=%HELPER_DATA_DIR%\scheduled-all-posters-refresh.log"
set "PLEX_LOG=%HELPER_DATA_DIR%\scheduled-plex-scan.log"

if not exist "%HELPER_DATA_DIR%" mkdir "%HELPER_DATA_DIR%"

echo ============================================================ > "%LOG_FILE%"
echo Kometa Helper scheduled poster refresh started at %DATE% %TIME% >> "%LOG_FILE%"
echo Running without Kometa dashboard. >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"

if not exist "%PYTHON_EXE%" (
  echo Kometa Python venv was not found: "%PYTHON_EXE%" >> "%LOG_FILE%"
  exit /b 1
)

if not exist "%KOMETA_SCRIPT%" (
  echo Kometa script was not found: "%KOMETA_SCRIPT%" >> "%LOG_FILE%"
  exit /b 1
)

if not exist "%QUICKSTART_CONFIG%" (
  echo Kometa config was not found: "%QUICKSTART_CONFIG%" >> "%LOG_FILE%"
  exit /b 1
)

echo Asking Plex to scan movie and show library folders... >> "%LOG_FILE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PLEX_REFRESH_SCRIPT%" -ConfigPath "%QUICKSTART_CONFIG%" -LogFile "%PLEX_LOG%" -LocationsJson "%LOCATIONS_JSON%"
if exist "%PLEX_LOG%" type "%PLEX_LOG%" >> "%LOG_FILE%"

copy /Y "%QUICKSTART_CONFIG%" "%KOMETA_RUN_CONFIG%" >nul
if errorlevel 1 (
  echo Could not copy Quickstart config to Kometa run config. >> "%LOG_FILE%"
  exit /b 1
)

echo Running Kometa for Movies and TV Shows... >> "%LOG_FILE%"
cd /d "%KOMETA_DIR%"
"%PYTHON_EXE%" "%KOMETA_SCRIPT%" --run --ignore-schedules --run-libraries "Movies|TV Shows" --config "%KOMETA_RUN_CONFIG%" >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

echo ============================================================ >> "%LOG_FILE%"
echo Kometa finished at %DATE% %TIME% with exit code %EXIT_CODE% >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"
exit /b %EXIT_CODE%
