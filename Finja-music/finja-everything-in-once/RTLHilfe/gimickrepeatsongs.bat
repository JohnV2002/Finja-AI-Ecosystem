@echo off
REM ======================================================================
REM           RTL 89.0 Repeat Counter - Launcher
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Module: RTL Helper - Repeat Detection
REM   Author: J. Apps (JohnV2002 / Sodakiller1)
REM   Version: 1.1.0
REM   Description: Launches Python-based repeat counter for RTL 89.0 source
REM
REM   Features:
REM     • Monitors now-playing file for song repeats
REM     • Tracks repeat counts in memory file
REM     • Generates repeat statistics
REM     • Configurable monitoring interval
REM
REM   Requirements:
REM     • Python 3.x installed
REM     • rtl_repeat_counter.py in same directory
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2026 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

setlocal ENABLEDELAYEDEXPANSION

REM ======================================================================
REM Startup Logging
REM ======================================================================

echo [RTL-Counter] Start time: %DATE% %TIME%
echo [RTL-Counter] Current directory: %CD%
echo [RTL-Counter] Script directory: %~dp0

REM ======================================================================
REM Configuration
REM ======================================================================

REM Determine script directory
set "SCRIPT_DIR=%~dp0"

REM Paths relative to RTLHilfe directory
set "NP_PATH=%SCRIPT_DIR%..\Nowplaying\nowplaying.txt"
set "OUT_DIR=%SCRIPT_DIR%..\Nowplaying"
set "MEM_FILE=%SCRIPT_DIR%..\Memory\repeat_counts.json"

REM ======================================================================
REM Directory Setup
REM ======================================================================

REM Ensure output directory exists
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%" 2>nul

REM Ensure memory file directory exists
for %%# in ("%MEM_FILE%") do (
    if not exist "%%~dp#" mkdir "%%~dp#" 2>nul
)

REM ======================================================================
REM Path Verification
REM ======================================================================

echo [RTL-Counter] Now-playing file: %NP_PATH%
echo [RTL-Counter] Output directory: %OUT_DIR%
echo [RTL-Counter] Memory file: %MEM_FILE%
echo.

REM ======================================================================
REM Python Executable Detection
REM ======================================================================

REM Use python from PATH (or specify fixed path if needed)
REM set "PYEXE=C:\Python311\python.exe"
set "PYEXE=python"

REM Verify Python is available
where %PYEXE% >nul 2>&1
if errorlevel 1 (
    echo [RTL-Counter] ERROR: Python not found in PATH
    echo [RTL-Counter] Please install Python 3 from https://www.python.org/
    pause
    exit /b 1
)

REM ======================================================================
REM Repeat Counter Launch
REM ======================================================================

echo [RTL-Counter] Starting repeat counter...
echo [RTL-Counter] Monitoring: %NP_PATH%
echo [RTL-Counter] Output to: %OUT_DIR%
echo [RTL-Counter] Memory: %MEM_FILE%
echo.

REM Log the exact command being executed
echo [RTL-Counter] Executing: "%PYEXE%" "%SCRIPT_DIR%rtl_repeat_counter.py"
echo [RTL-Counter] Arguments: --np "%NP_PATH%" --outdir "%OUT_DIR%" --memfile "%MEM_FILE%" --interval 2
echo.

REM Start the repeat counter
"%PYEXE%" "%SCRIPT_DIR%rtl_repeat_counter.py" ^
  --np "%NP_PATH%" ^
  --outdir "%OUT_DIR%" ^
  --memfile "%MEM_FILE%" ^
  --interval 2

REM ======================================================================
REM Exit Handling
REM ======================================================================

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [RTL-Counter] ERROR: Counter exited with error code: %ERRORLEVEL%
    echo [RTL-Counter] Please check the error messages above
) else (
    echo.
    echo [RTL-Counter] Counter terminated normally.
)

echo [RTL-Counter] Script finished.
echo.
pause
endlocal