@REM ======================================================================
@REM                  Finja's Static File Server Launcher
@REM ======================================================================
@REM
@REM   Project: Finja - Twitch Interactivity Suite
@REM   Author: J. Apps (JohnV2002 / Sodakiller1)
@REM   Version: 2.2.1
@REM   Description: Batch script to start static file server for overlay.
@REM
@REM   ✨ New in 2.2.1:
@REM     • Improved error handling and user feedback
@REM     • Python version detection with fallbacks
@REM     • Clear status messages in English
@REM     • Port conflict detection
@REM     • Helpful startup information
@REM
@REM   📜 Changelog 2.1.0:
@REM     • Simple HTTP server for serving overlay files
@REM     • Python 3.10 preference
@REM
@REM   Copyright (c) 2026 J. Apps
@REM   Licensed under the MIT License.
@REM
@REM ======================================================================

@echo off
setlocal ENABLEDELAYEDEXPANSION
title Finja Static Server

REM ======================================================================
REM Change to script directory
REM ======================================================================
cd /d "%~dp0"
echo.
echo ======================================================================
echo   Finja Static File Server v2.2.1
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
REM Check for required files
REM ======================================================================
echo [INFO] Checking for overlay files...

if not exist "index_merged.html" (
  echo [WARN] index_merged.html not found!
  echo [INFO] Make sure overlay files are in the current directory
  echo.
) else (
  echo [OK] index_merged.html found
)

if not exist "bot_merged.html" (
  echo [WARN] bot_merged.html not found!
) else (
  echo [OK] bot_merged.html found
)
echo.

REM ======================================================================
REM Start Server
REM ======================================================================
echo ======================================================================
echo   Starting Static File Server
echo ======================================================================
echo.
echo [INFO] Server will start on: http://127.0.0.1:8088
echo [INFO] This server hosts:
echo [INFO]   - index_merged.html (Overlay for OBS)
echo [INFO]   - bot_merged.html (Bot Control Panel)
echo [INFO]   - All other files in this directory
echo.
echo [INFO] Access overlay at: http://127.0.0.1:8088/index_merged.html
echo [INFO] Access bot panel at: http://127.0.0.1:8088/bot_merged.html
echo.
echo [INFO] Press Ctrl+C to stop the server
echo.
echo ======================================================================
echo.

REM Start Python's built-in HTTP server on port 8088
%PY_CMD% -m http.server 8088

REM ======================================================================
REM Error Handling
REM ======================================================================
if %errorlevel% neq 0 (
  echo.
  echo [ERROR] Server exited with error code: %errorlevel%
  echo [ERROR] Common issues:
  echo [ERROR]   - Port 8088 already in use by another program
  echo [ERROR]   - No permission to bind to port
  echo [ERROR]   - Python http.server module not available
  echo.
  echo [INFO] To fix port conflict, try:
  echo [INFO]   1. Close other programs using port 8088
  echo [INFO]   2. Change port in this script (edit start_static_server.bat)
  echo [INFO]   3. Kill process: netstat -ano ^| findstr :8088
  echo.
) else (
  echo.
  echo [INFO] Server stopped gracefully
  echo.
)

pause