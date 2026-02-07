@echo off
@REM ======================================================================
@REM          Start Now Playing - TruckersFM Windows Launcher
@REM ======================================================================
@REM
@REM   Project: Finja - Twitch Interactivity Suite
@REM   Module: finja-music-standalone
@REM   Author: J. Apps (JohnV2002 / Sodakiller1)
@REM   Version: 1.0.2
@REM
@REM ----------------------------------------------------------------------
@REM
@REM   Copyright (c) 2026 J. Apps
@REM   Licensed under the MIT License.
@REM
@REM
@REM ======================================================================

cd /d "%~dp0"
python -m pip install --upgrade pip requests beautifulsoup4 >nul 2>&1
python truckersfm_nowplaying.py --out nowplaying.txt --interval 10
pause