@echo off
setlocal ENABLEDELAYEDEXPANSION


@echo off
REM ======================================================================
REM                      Finja's Brain & Knowledge Core - 89.0 RTL
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Author: JohnV2002 (J. Apps / Sodakiller1)
REM   Version: 1.0.0 (89.0 RTL Modul)
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2025 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================


REM === Config ===
set PORT=9222
set DEBUG=0
set DEBOUNCE_MS=6000
set REPEAT_GAP_S=90

set "PROFILE_DIR=%USERPROFILE%\AppData\Local\Temp\chrome_cdp_profile_%PORT%"
set "OUTFILE=%USERPROFILE%\Pictures\Streaming\RTL980\nowplaying.txt"

set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

REM Use the faster Radioplayer page (NOT the main 89.0 RTL site)
set "URL=https://sites.89.0rtl.de/radioplayer/live/index.html"

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
set "SCRIPT_DIR=%~dp0"
set "DBG="
if "%DEBUG%"=="1" set "DBG=--debug"

python "%SCRIPT_DIR%rtl89_cdp_nowplaying.py" ^
  --port %PORT% ^
  --out "%OUTFILE%" ^
  --interval 5 ^
  --debounce %DEBOUNCE_MS% ^
  --repeat-gap %REPEAT_GAP_S% ^
  %DBG%

endlocal
