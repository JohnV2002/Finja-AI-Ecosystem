@echo off
setlocal ENABLEDELAYEDEXPANSION
REM Setze Codepage auf UTF-8 für Emojis
chcp 65001 >nul

REM ======================================================================
REM            Finja's Music Module - All-in-One Server Launcher
REM ======================================================================
REM
REM    Project: Finja - Twitch Interactivity Suite
REM    Module: finja-everything-in-one
REM    Author: J. Apps (JohnV2002 / Sodakiller1)
REM    Version: 1.1.0
REM    Description: Starts the central Python web server (webserver.py)
REM
REM    ✨ New in 1.1.0:
REM      • Professional English documentation
REM      • Python version detection with fallbacks
REM      • Improved error handling
REM
REM ----------------------------------------------------------------------
REM
REM    Copyright (c) 2026 J. Apps
REM    Licensed under the MIT License.
REM ======================================================================

REM Wechsel ins Skript-Verzeichnis
cd /d "%~dp0"

echo.
echo ======================================================================
echo    Finja's Music Module - All-in-One Server v1.1.0
echo ======================================================================
echo.

REM ======================================================================
REM 1. Python finden (Robust Version)
REM ======================================================================
echo [INFO] Detecting Python installation...

set PY_CMD=

REM Versuch 1: Python Launcher (py) mit Version 3.10
py -3.10 --version >nul 2>&1
if !errorlevel! equ 0 (
    set PY_CMD=py -3.10
    echo [OK] Using Python 3.10 via Launcher
    goto :FOUND
)

REM Versuch 2: Python Launcher (py) allgemein
py --version >nul 2>&1
if !errorlevel! equ 0 (
    set PY_CMD=py
    echo [OK] Using default Python via Launcher
    goto :FOUND
)

REM Versuch 3: Standard 'python' Befehl
python --version >nul 2>&1
if !errorlevel! equ 0 (
    set PY_CMD=python
    echo [OK] Using standard 'python' command
    goto :FOUND
)

:NOT_FOUND
echo.
echo [ERROR] Python not found in PATH!
echo [ERROR] Please install Python 3.10+ from python.org.
echo.
pause
exit /b 1

:FOUND
echo [INFO] Python version:
%PY_CMD% --version
echo.

REM ======================================================================
REM 2. Webserver Datei prüfen
REM ======================================================================
if not exist "webserver.py" (
    echo [ERROR] webserver.py not found in current directory!
    echo.
    pause
    exit /b 1
)

REM ======================================================================
REM 3. Starten
REM ======================================================================
echo ======================================================================
echo    Starting Finja's Music Module Server
echo ======================================================================
echo.
echo [INFO] Server will handle:
echo [INFO]    - Music playback control
echo [INFO]    - Spotify integration
echo [INFO]    - VLC control
echo [INFO]    - Module coordination
echo.
echo [INFO] Press Ctrl+C to stop the server
echo.

%PY_CMD% webserver.py

REM Fehler beim Beenden abfangen
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server exited with error code: %errorlevel%
    echo [ERROR] Common issues:
    echo [ERROR]    - Missing dependencies (pip install -r requirements.txt)
    echo [ERROR]    - Port 8022 already in use
) else (
    echo.
    echo [INFO] Server stopped gracefully.
)

pause