@echo off
setlocal ENABLEDELAYEDEXPANSION
REM ------------------------------------------------------------
REM run_finja.bat — robust + 'force' via FINJA_FORCE=1
REM ------------------------------------------------------------

@echo off
REM ======================================================================
REM                      Finja's Brain & Knowledge Core - Spotify
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Author: JohnV2002 (J. Apps / Sodakiller1)
REM   Version: 1.0.0 (Spotify Modul)
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2025 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

cd /d "%~dp0"
set "LOCK_FILE=.finja_min_writer.lock"

REM force: Lock ignorieren (und optional löschen)
if /i "%~1"=="force" (
  set "FINJA_FORCE=1"
  if exist "%LOCK_FILE%" (
    echo [i] Entferne alte Lock-Datei: "%LOCK_FILE%"
    attrib -h -s -r "%LOCK_FILE%" >nul 2>&1
    del /f /q "%LOCK_FILE%" >nul 2>&1
  )
)

REM Diagnose: zeigen, ob Lock (sichtbar oder versteckt) existiert
for /f "tokens=*" %%A in ('dir /a /b "%LOCK_FILE%" 2^>nul') do set "LOCK_FOUND=1"
if defined LOCK_FOUND (
  if not defined FINJA_FORCE (
    echo [i] Lock vorhanden: "%LOCK_FILE%"
    echo     Wenn das nicht stimmt: run_finja.bat force
    echo.
    pause
    exit /b 0
  ) else (
    echo [i] FINJA_FORCE aktiv – Lock wird ignoriert.
  )
)

REM Python finden
where python >nul 2>&1 && (set "PYEXE=python") || (
  where py >nul 2>&1 && (set "PYEXE=py -3") || (
    echo [x] Python wurde nicht gefunden. Bitte Python 3.x installieren oder PATH setzen.
    pause & exit /b 1
  )
)

echo [i] Starte Finja Minimal Writer...
set FINJA_FORCE=%FINJA_FORCE%
"%PYEXE%" -X dev finja_min_writer.py
set "RC=%ERRORLEVEL%"
echo.

if %RC%==0 (
  echo [i] Finja Minimal Writer beendet.
) else (
  echo [!] Finja Minimal Writer mit Code %RC% beendet.
)
pause
exit /b %RC%
