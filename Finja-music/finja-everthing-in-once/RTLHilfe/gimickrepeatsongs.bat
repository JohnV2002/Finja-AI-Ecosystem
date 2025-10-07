@echo off
REM ======================================================================
REM             Finja's Brain & Knowledge Core - RTL Repeat Counter Starter
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Author: JohnV2002 (J. Apps / Sodakiller1)
REM   Version: 1.0.0 (RTL Modul)
REM
REM   Description: Startet den Python-basierten Wiederholungszähler
REM                (`rtl_repeat_counter.py`) für die 89.0 RTL Quelle.
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2025 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

@echo off
setlocal

REM === DEBUGGING: Logge den Start der Batch-Datei ===
echo [RTL Repeat Counter .bat] Startzeitpunkt: %DATE% %TIME%
echo [RTL Repeat Counter .bat] Aktuelles Verzeichnis: %CD%
echo [RTL Repeat Counter .bat] Skript-Verzeichnis (SCRIPT_DIR): %~dp0
REM ================================================

REM === Config (Pfade anpassen!) ===
set "SCRIPT_DIR=%~dp0"
REM Pfade relativ zum RTLHilfe-Ordner
set "NP_PATH=%SCRIPT_DIR%..\Nowplaying\nowplaying.txt"
set "OUT_DIR=%SCRIPT_DIR%..\Nowplaying"
set "MEM_FILE=%SCRIPT_DIR%..\Memory\repeat_counts.json"

REM === Sicherstellen, dass Verzeichnisse existieren ===
mkdir "%OUT_DIR%" 2>nul
for %%# in ("%MEM_FILE%") do mkdir "%%~dp#" 2>nul

REM === DEBUGGING: Logge die berechneten Pfade ===
echo [RTL Repeat Counter .bat] NP_PATH: %NP_PATH%
echo [RTL Repeat Counter .bat] OUT_DIR: %OUT_DIR%
echo [RTL Repeat Counter .bat] MEM_FILE: %MEM_FILE%
REM ================================================

REM === Starte den Repeat-Counter (KEIN CHROME!) ===
echo [RTL Repeat Counter] Starte Zaehler...
echo [RTL Repeat Counter] Ueberwache: %NP_PATH%
echo [RTL Repeat Counter] Ausgabe in:   %OUT_DIR%
echo [RTL Repeat Counter] Speicherort: %MEM_FILE%
echo.

REM Verwende python aus dem PATH oder einen festen Pfad
REM set "PYEXE=C:\Python311\python.exe"
set "PYEXE=python"

REM === DEBUGGING: Logge den Python-Aufruf ===
echo [RTL Repeat Counter .bat] Fuehre aus: "%PYEXE%" "%SCRIPT_DIR%rtl_repeat_counter.py" --np "%NP_PATH%" --outdir "%OUT_DIR%" --memfile "%MEM_FILE%" --interval 2
REM ================================================

"%PYEXE%" "%SCRIPT_DIR%rtl_repeat_counter.py" ^
  --np "%NP_PATH%" ^
  --outdir "%OUT_DIR%" ^
  --memfile "%MEM_FILE%" ^
  --interval 2

REM === DEBUGGING: Logge das Ergebnis ===
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [RTL Repeat Counter] Fehler beim Starten des Zaehlers. Exit-Code: %ERRORLEVEL%
) else (
    echo.
    echo [RTL Repeat Counter] Skript beendet.
)
echo [RTL Repeat Counter .bat] Ende.
pause
endlocal