@echo off
REM ======================================================================
REM           RTL 89.0 Chrome DevTools Protocol Launcher
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Module: RTL Helper - Browser Automation
REM   Author: J. Apps (JohnV2002 / Sodakiller1)
REM   Version: 1.1.0
REM   Description: Launches Chrome with CDP and starts RTL now-playing scraper
REM
REM   Features:
REM     • Launches Chrome with remote debugging enabled
REM     • Connects to RTL 89.0 Radioplayer
REM     • Monitors now-playing information via CDP
REM     • Automatic dependency installation
REM     • Configurable debounce and repeat detection
REM
REM   Requirements:
REM     • Google Chrome installed
REM     • Python 3.x with pip
REM     • websocket-client and requests packages (auto-installed)
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2026 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

setlocal ENABLEDELAYEDEXPANSION

REM ======================================================================
REM Configuration
REM ======================================================================

REM Chrome DevTools Protocol port
set PORT=9222

REM Debug mode (0=off, 1=on)
set DEBUG=0

REM Debounce time in milliseconds (avoid duplicate detections)
set DEBOUNCE_MS=6000

REM Minimum gap between repeat detections in seconds
set REPEAT_GAP_S=90

REM Chrome profile directory (isolated from main browser)
set "PROFILE_DIR=%USERPROFILE%\AppData\Local\Temp\chrome_cdp_profile_%PORT%"

REM ======================================================================
REM Path Detection
REM ======================================================================

REM Chrome executable location (try common paths)
set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

REM Use the faster Radioplayer page (NOT the main 89.0 RTL site)
set "URL=https://sites.89.0rtl.de/radioplayer/live/index.html"

REM Determine script directory
set "SCRIPT_DIR=%~dp0"
if not "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR%\"

REM Determine project root (one level up from script directory)
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

REM Output file for now-playing information
set "OUTPUT_FILE=%PROJECT_ROOT%\Nowplaying\nowplaying.txt"

REM Log directory (optional)
set "LOG_DIR=%PROJECT_ROOT%\logs"

REM ======================================================================
REM Chrome Launcher
REM ======================================================================

REM Ensure profile directory exists
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%" >nul 2>&1

REM Start isolated Chrome with DevTools Protocol enabled
echo [RTL-CDP] Starting Chrome with remote debugging on port %PORT%...
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

REM ======================================================================
REM DevTools Connection Check
REM ======================================================================

echo [RTL-CDP] Waiting for Chrome DevTools on port %PORT%...
powershell -NoProfile -Command "for($i=0;$i -lt 60;$i++){ try { $r = iwr http://127.0.0.1:%PORT%/json/version -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0} } catch{} Start-Sleep -Milliseconds 300 } exit 1"

if errorlevel 1 (
    echo [RTL-CDP] ERROR: DevTools not reachable after 18 seconds
    echo [RTL-CDP] Please check if Chrome started correctly
    exit /b 1
)

echo [RTL-CDP] DevTools ready!

REM ======================================================================
REM Dependency Check & Installation
REM ======================================================================

echo [RTL-CDP] Checking Python dependencies...

REM Check if pip is available
where pip >nul 2>&1
if errorlevel 1 (
    echo [RTL-CDP] ERROR: Python/pip not found in PATH
    echo [RTL-CDP] Please install Python 3 from https://www.python.org/
    exit /b 1
)

REM Install required packages if missing
pip show websocket-client >nul 2>&1
if errorlevel 1 (
    echo [RTL-CDP] Installing websocket-client...
    pip install --upgrade websocket-client
)

pip show requests >nul 2>&1
if errorlevel 1 (
    echo [RTL-CDP] Installing requests...
    pip install --upgrade requests
)

echo [RTL-CDP] Dependencies OK!

REM ======================================================================
REM Python Scraper Launch
REM ======================================================================

REM Set debug flag if enabled
set "DBG="
if "%DEBUG%"=="1" set "DBG=--debug"

echo [RTL-CDP] Output file: %OUTPUT_FILE%
echo [RTL-CDP] Project root: %PROJECT_ROOT%
echo [RTL-CDP] Starting now-playing scraper...

python "%SCRIPT_DIR%rtl89_cdp_nowplaying.py" ^
  --port %PORT% ^
  --out "%OUTPUT_FILE%" ^
  --interval 5 ^
  --debounce %DEBOUNCE_MS% ^
  --repeat-gap %REPEAT_GAP_S% ^
  %DBG%

REM ======================================================================
REM Cleanup
REM ======================================================================

echo [RTL-CDP] Scraper terminated.
endlocal