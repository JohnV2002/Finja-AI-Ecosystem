@echo off
setlocal ENABLEDELAYEDEXPANSION

REM === Config ===
set PORT=9222
set DEBUG=0
set DEBOUNCE_MS=6000
set REPEAT_GAP_S=90

set "PROFILE_DIR=%USERPROFILE%\AppData\Local\Temp\chrome_cdp_profile_%PORT%"

REM === NEU: Absolute Pfade fuer Chrome und Skript-Ordner ===
set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

REM Use the faster Radioplayer page (NOT the main 89.0 RTL site)
set "URL=https://sites.89.0rtl.de/radioplayer/live/index.html"

REM === NEU: Absolute Pfade fuer Ein- und Ausgabe ===
REM Gehe vom Skript-Verzeichnis aus, um die Pfade zu bestimmen
set "SCRIPT_DIR=%~dp0"
REM Stelle sicher, dass SCRIPT_DIR mit \ endet
if not "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR%\"

REM Bestimme die absoluten Pfade fuer Ein- und Ausgabe relativ zum Skript-Ordner
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
set "OUTPUT_FILE=%PROJECT_ROOT%\Nowplaying\nowplaying.txt"
set "LOG_DIR=%PROJECT_ROOT%\logs"
REM ===============================

REM === Ensure profile dir exists ===
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%" >nul 2>&1

REM === Start isolated Chrome with DevTools; allow all origins to avoid 403
start "" "%CHROME_EXE%" ^
  --user-data-dir="%PROFILE_DIR%" ^
  --remote-debugging-port=%PORT% ^
  --remote-allow-origins=* ^
  --disable-background-mode ^
  --no-first-run ^
  --no-default-browser-check ^
  --disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling,TabFreeze,TabHoverCardImages ^
  --disable-ipc-flooding-protection ^
  --disable-background-networking ^
  "%URL%"

REM === Wait until DevTools is ready ===
echo Waiting for Chrome DevTools on %PORT% ...
powershell -NoProfile -Command "for($i=0;$i -lt 60;$i++){ try { $r = iwr http://127.0.0.1:%PORT%/json/version -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0} } catch{} Start-Sleep -Milliseconds 300 } exit 1" || (echo DevTools not reachable & exit /b 1)

REM === Install deps if missing ===
where pip >nul 2>&1 || (echo Python/pip not found in PATH. Please install Python 3. & exit /b 1)
pip show websocket-client >nul 2>&1 || pip install --upgrade websocket-client requests

REM === Run scraper (assumes .py is next to this .bat) ===
set "DBG="
if "%DEBUG%"=="1" set "DBG=--debug"

REM === NEU: Gebe den OUTPUT_FILE explizit an ===
echo [rtl89-cdp] OUTPUT_FILE wird gesetzt auf: %OUTPUT_FILE%
echo [rtl89-cdp] PROJECT_ROOT ist: %PROJECT_ROOT%

python "%SCRIPT_DIR%rtl89_cdp_nowplaying.py" ^
  --port %PORT% ^
  --out "%OUTPUT_FILE%" ^
  --interval 5 ^
  --debounce %DEBOUNCE_MS% ^
  --repeat-gap %REPEAT_GAP_S% ^
  %DBG%

endlocal