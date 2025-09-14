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
setlocal
set PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
%PS% -NoLogo -ExecutionPolicy Bypass -File "%~dp0Review-ArtistNotSure.ps1" ^
  -QueuePath "missingsongs/artist_not_sure.jsonl" ^
  -KbPath "SongsDB/songs_kb.json" ^
  -ReviewedPath "missingsongs/artist_not_sure.reviewed.jsonl" ^
  -Backup -NotesMode json -AllowTitleOnly -MaxAmbiguous 3
endlocal
