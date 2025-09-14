@echo off
setlocal
cd /d "%~dp0"

REM ======================================================================
REM                      Finja's Brain & Knowledge Core - MDR
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Author: JohnV2002 (J. Apps / Sodakiller1)
REM   Version: 1.0.0 (MDR Modul)
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2025 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

REM --- Ensure config exists
if not exist "config_mdr.json" (
  echo [ERR] config_mdr.json not found next to this .bat
  pause
  exit /b 1
)

REM --- Copy to the expected default name (used by finja_min_writer.py)
copy /Y "config_mdr.json" "config_min.json" >nul

REM --- Ensure outputs & cache dirs (adjust if paths changed in config)
if not exist "outputs" (
  mkdir "outputs" 2>nul
)
if not exist "cache" (
  mkdir "cache" 2>nul
)

REM --- Pick Python
set "PYEXE="
where python >nul 2>&1 && set "PYEXE=python"
if "%PYEXE%"=="" ( where py >nul 2>&1 && set "PYEXE=py -3" )
if "%PYEXE%"=="" (
  echo [ERR] Python not found. Install Python 3 and add it to PATH.
  pause
  exit /b 1
)

REM --- Run Finja
%PYEXE% -u finja_min_writer.py
set "EC=%ERRORLEVEL%"

REM Ctrl+C liefert meist 0xC000013A -> 3221225786 (oder -1073741510)
if "%EC%"=="3221225786" goto :graceful_bye
if "%EC%"=="-1073741510" goto :graceful_bye

if not "%EC%"=="0" (
  echo.
  echo [ERR] finja_min_writer.py exited with code %EC%
  echo (Config wurde in config_min.json kopiert; Pfade pruefen, falls es wieder passiert.)
  pause
  exit /b %EC%
)
goto :eof

:graceful_bye
chcp 65001 >nul
echo.
powershell -NoProfile -Command "Write-Host '[exit] bye 👋❤'"
exit /b 0