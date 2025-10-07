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



@echo off
cd /d "%~dp0"
python -m pip install --upgrade pip requests >nul 2>&1
IF NOT EXIST spotify_config.json (
  echo { "output":"nowplaying_spotify.txt", "interval":5, "spotify": { "client_id":"YOUR_ID", "client_secret":"YOUR_SECRET", "refresh_token":"YOUR_REFRESH_TOKEN" } } > spotify_config.json
  echo Created spotify_config.json - edit your credentials.
  pause
  exit /b 0
)
python spotify_nowplaying.py --config spotify_config.json
pause
