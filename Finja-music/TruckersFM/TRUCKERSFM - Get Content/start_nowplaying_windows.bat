@echo off
REM ======================================================================
REM                      Finja's Brain & Knowledge Core - TruckersFM
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Author: JohnV2002 (J. Apps / Sodakiller1)
REM   Version: 1.0.0 (TruckersFM Modul)
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2025 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

@echo off
cd /d "%~dp0"
python -m pip install --upgrade pip requests beautifulsoup4 >nul 2>&1
python truckersfm_nowplaying.py --out nowplaying.txt --interval 10
pause
