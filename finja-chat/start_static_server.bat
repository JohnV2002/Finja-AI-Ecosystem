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
title Finja Static Server
cd /d "%~dp0"
echo Starte Finja Static Server auf http://127.0.0.1:8088 ...
py -3.10 -m http.server 8088
pause