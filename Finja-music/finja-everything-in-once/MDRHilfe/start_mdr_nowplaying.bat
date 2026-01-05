@echo off
@REM ======================================================================
@REM             Finja's Brain & Knowledge Core - MDR Starter
@REM ======================================================================
@REM
@REM   Project: Finja - Twitch Interactivity Suite
@REM   Author: J. Apps (JohnV2002 / Sodakiller1)
@REM   Version: 1.1.0 (MDR Module)
@REM
@REM   Description: Starts the Python crawler (mdr_nowplaying.py) that fetches
@REM                the currently playing song from MDR Sachsen-Anhalt.
@REM
@REM   New in 1.1.0:
@REM     - Complete English documentation
@REM     - All comments and messages translated to English
@REM     - Copyright updated to 2026
@REM     - Fixed duplicate code block
@REM
@REM ----------------------------------------------------------------------
@REM  Features:
@REM ----------------------------------------------------------------------
@REM   - Starts the MDR "Get Content" module with a double-click.
@REM   - Automatically searches for the installed Python version (py, python, etc.).
@REM   - Checks if required Python packages (requests, defusedxml) are present
@REM     and installs them automatically if needed.
@REM   - Ensures the console stays open for log output.
@REM
@REM ----------------------------------------------------------------------
@REM
@REM   Copyright (c) 2026 J. Apps
@REM   Licensed under the MIT License.
@REM
@REM ======================================================================

setlocal ENABLEDELAYEDEXPANSION
title MDR NowPlaying Starter
chcp 65001 >nul
cd /d "%~dp0"

echo(
echo ==============================
echo   MDR NowPlaying - Starter
echo ==============================
echo  Folder: %CD%
echo(

@REM -------------------------------
@REM  (OPTIONAL) Customize Region/URLs
@REM  -> Uncomment and set as needed
@REM set MDR_XML_URL=https://www.mdr.de/XML/titellisten/mdr1_sa_2.xml  
@REM set MDR_STREAM_URL=https://mdr-284290-1.sslcast.mdr.de/mdr/284290/1/mp3/high/stream.mp3  
@REM set MDR_HTML_URL=https://www.mdr.de/mdr-sachsen-anhalt/titelliste-mdr-sachsen-anhalt--102.html  
@REM set MDR_POLL_S=10
@REM -------------------------------

@REM ---- Find Python (py -3, py, python, python3) ----
set "PYCMD="
call :trycmd "py -3" && set "PYCMD=py -3"
if not defined PYCMD call :trycmd "py"      && set "PYCMD=py"
if not defined PYCMD call :trycmd "python"  && set "PYCMD=python"
if not defined PYCMD call :trycmd "python3" && set "PYCMD=python3"

if not defined PYCMD (
  echo [ERR] Python not found. Please install and add to PATH.
  echo       Download: https://www.python.org/downloads/  
  echo       Tip: Check "Add Python to PATH" during installation.
  echo(
  pause
  exit /b 1
)

for /f "tokens=2,*" %%a in ('%PYCMD% -V 2^>^&1') do set "PYVER=%%a"
echo [i] Python: %PYCMD%  (Version %PYVER%)
echo(

@REM ---- Install dependencies silently ----
echo [i] Checking/Installing dependencies...
%PYCMD% -m pip show requests    >nul 2>&1 || %PYCMD% -m pip install --user -q requests
%PYCMD% -m pip show defusedxml  >nul 2>&1 || %PYCMD% -m pip install --user -q defusedxml
@REM BeautifulSoup is not needed for the pure XML variant;
@REM if you use HTML fallback, you can enable the next line:
@REM %PYCMD% -m pip show beautifulsoup4 >nul 2>&1 || %PYCMD% -m pip install --user -q beautifulsoup4
echo [i] OK.
echo(

echo [i] Starting MDR NowPlaying...
echo [i] Output: nowplaying.txt  ^|  Source: now_source.txt
echo(

@REM ---- Start script (unbuffered logs) ----
%PYCMD% -u mdr_nowplaying.py --out nowplaying.txt
set "RC=%ERRORLEVEL%"

echo(
echo [i] Script finished. Exit code: %RC%
echo     (Window stays open to read logs.)
echo(
pause >nul
exit /b %RC%

:trycmd
@REM Check if a Python command works (outputs version)
%~1 -V >nul 2>&1
exit /b %ERRORLEVEL%