@REM ======================================================================
@REM                      Finja's Twitch Bot & Overlay
@REM ======================================================================
@REM
@REM   Project: Finja - Twitch Interactivity Suite
@REM   Author: JohnV2002 (J. Apps / Sodakiller1)
@REM   Version: 2.1.0
@REM   Description: Batch script to start a server component.
@REM
@REM   Copyright (c) 2025 J. Apps
@REM   Licensed under the MIT License.
@REM
@REM ======================================================================

@echo off
REM Start server and guarantee .env is loaded via python-dotenv launcher
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3.10 -V >nul 2>&1
  if %errorlevel%==0 ( set PY_CMD=py -3.10 ) else ( set PY_CMD=py )
) else (
  set PY_CMD=python
)

echo Using: %PY_CMD%
%PY_CMD% -m dotenv run -- uvicorn spotify_request_server_env:app --port 8099 --reload
pause
