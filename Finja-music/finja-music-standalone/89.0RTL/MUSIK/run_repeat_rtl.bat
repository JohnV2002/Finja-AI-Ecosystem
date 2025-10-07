@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

REM ======================================================================
REM                      Finja's Brain & Knowledge Core - 89.0 RTL
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Author: JohnV2002 (J. Apps / Sodakiller1)
REM   Version: 1.0.1 (89.0 RTL Modul - Sterilized)
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2025 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

REM --- Relative Pfade (GitHub-ready)
set "NP_PATH=nowplaying.txt"
set "OUT_DIR=outputs"
set "MEM_FILE=Memory/repeat_counts.json"

echo [i] Finja RTL Repeat Counter v1.0.1
echo [i] Working directory: %CD%
echo.

if not exist "rtl_repeat_counter.py" (
  echo [ERR] rtl_repeat_counter.py nicht gefunden!
  pause
  exit /b 1
)

REM --- Verzeichnisse erstellen
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%" 2>nul
for %%# in ("%MEM_FILE%") do if not exist "%%~dp#" mkdir "%%~dp#" 2>nul

REM --- Python detection
set "PYEXE="
where python >nul 2>&1 && set "PYEXE=python"
if "%PYEXE%"=="" ( where py >nul 2>&1 && set "PYEXE=py -3" )
if "%PYEXE%"=="" (
  echo [ERR] Python nicht gefunden. Bitte Python 3 installieren.
  pause
  exit /b 1
)

echo [i] Python gefunden: 
"%PYEXE%" --version
echo.

REM --- Script starten
echo [i] Starte RTL Repeat Counter...
echo.

"%PYEXE%" -u rtl_repeat_counter.py --np "%NP_PATH%" --outdir "%OUT_DIR%" --memfile "%MEM_FILE%" --interval 2

set "EC=%ERRORLEVEL%"

REM --- Exit-Code handling
if "%EC%"=="0" (
  echo.
  echo [i] Script erfolgreich beendet 👋
) else (
  echo.
  echo [ERR] Script mit Fehler beendet: Code %EC%
  echo [i] Tipp: Prüfe die Pfade in der Konfiguration
)

pause
exit /b %EC%