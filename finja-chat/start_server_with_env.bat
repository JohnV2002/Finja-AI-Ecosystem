@REM ======================================================================
@REM                  Finja's Song Request Server Launcher
@REM ======================================================================
@REM
@REM   Project: Finja - Twitch Interactivity Suite
@REM   Author: J. Apps (JohnV2002 / Sodakiller1)
@REM   Version: 2.3.0
@REM   Description: Batch script to start Spotify song request server.
@REM
@REM   ✨ New in 2.3.0:
@REM     • Merged Production + GitHub tracks (2026-07-19)
@REM     • .env now lives in private/ (never synced to GitHub)
@REM     • FINJA_BRIDGE flag restored from Production
@REM
@REM   📜 Changelog 2.2.1 (GitHub track):
@REM     • Improved error handling and user feedback
@REM     • Python version detection with fallbacks
@REM     • Dependency check before starting server
@REM
@REM   📜 Changelog 2.1.0 (Production track):
@REM     • Automatic .env loading via python-dotenv
@REM     • Python launcher (py) with version preference
@REM     • Uvicorn auto-reload for development
@REM
@REM   Copyright (c) 2026 J. Apps
@REM   Licensed under the MIT License.
@REM
@REM ======================================================================

@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ======================================================================
REM Change to script directory
REM ======================================================================
cd /d "%~dp0"

REM Feature flag consumed by the overlay/bot panel -- keep set even though
REM this launcher itself doesn't read it.
set FINJA_BRIDGE=1

echo.
echo ======================================================================
echo   Finja Song Request Server Launcher v2.3.0
echo ======================================================================
echo.

REM ======================================================================
REM Detect Python Installation
REM ======================================================================
echo [INFO] Detecting Python installation...

REM Try Python launcher first (Windows recommended way)
where py >nul 2>&1
if %errorlevel%==0 (
  echo [OK] Python launcher (py) found

  REM Prefer Python 3.10 if available
  py -3.10 --version >nul 2>&1
  if %errorlevel%==0 (
    set PY_CMD=py -3.10
    echo [OK] Using Python 3.10
  ) else (
    set PY_CMD=py
    echo [INFO] Python 3.10 not found, using default Python
  )
) else (
  REM Fallback to python command
  where python >nul 2>&1
  if %errorlevel%==0 (
    set PY_CMD=python
    echo [OK] Python command found
  ) else (
    echo [ERROR] Python not found in PATH!
    echo [ERROR] Please install Python 3.10 or higher from python.org
    echo.
    pause
    exit /b 1
  )
)

REM Display Python version
echo.
echo [INFO] Python version:
%PY_CMD% --version
echo.

REM ======================================================================
REM Check for .env file (lives in private/, never synced to GitHub)
REM ======================================================================
if not exist "private\.env" (
  echo [WARN] private\.env file not found!
  echo [WARN] Make sure you have created private\.env with your Spotify credentials:
  echo [WARN]   - SPOTIPY_CLIENT_ID
  echo [WARN]   - SPOTIPY_CLIENT_SECRET
  echo [WARN]   - SPOTIPY_REDIRECT_URI
  echo [INFO] See .env.example in this folder for the full list.
  echo.
  echo [INFO] Continuing anyway... you can add private\.env later
  echo.
) else (
  echo [OK] private\.env file found
  echo.
)

REM ======================================================================
REM Check Dependencies
REM ======================================================================
echo [INFO] Checking dependencies...

%PY_CMD% -c "import fastapi, spotipy, dotenv, uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
  echo [WARN] Some dependencies might be missing!
  echo [INFO] Installing required packages...
  echo.
  %PY_CMD% -m pip install fastapi spotipy python-dotenv uvicorn[standard] --quiet
  if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies!
    echo [ERROR] Please run manually: pip install fastapi spotipy python-dotenv uvicorn[standard]
    echo.
    pause
    exit /b 1
  )
  echo [OK] Dependencies installed
  echo.
) else (
  echo [OK] All dependencies found
  echo.
)

REM ======================================================================
REM Start Server
REM ======================================================================
echo ======================================================================
echo   Starting Finja Song Request Server
echo ======================================================================
echo.
echo [INFO] Server will start on: http://127.0.0.1:8099
echo [INFO] API endpoints:
echo [INFO]   - GET  /health   - Health check
echo [INFO]   - GET  /pending  - List pending requests
echo [INFO]   - GET  /devices  - List Spotify devices
echo [INFO]   - POST /chat     - Handle chat commands
echo.
echo [INFO] Press Ctrl+C to stop the server
echo.
echo ======================================================================
echo.

REM Start server with dotenv support -- .env lives in private/ now
%PY_CMD% -m dotenv -f private\.env run -- uvicorn spotify_request_server_env:app --host 127.0.0.1 --port 8099 --reload

REM ======================================================================
REM Error Handling
REM ======================================================================
if %errorlevel% neq 0 (
  echo.
  echo [ERROR] Server exited with error code: %errorlevel%
  echo [ERROR] Common issues:
  echo [ERROR]   - spotify_request_server_env.py not found in current directory
  echo [ERROR]   - Invalid Spotify credentials in private\.env
  echo [ERROR]   - Port 8099 already in use
  echo.
) else (
  echo.
  echo [INFO] Server stopped gracefully
  echo.
)

pause
