@echo off
REM ======================================================================
REM             Finja's Brain & Knowledge Core - All-in-One Server Starter
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Author: JohnV2002 (J. Apps / Sodakiller1)
REM   Version: 1.0.0 (All-in-One Modul)
REM
REM   Description: Startet den zentralen Python-Webserver (webserver.py),
REM                der als Steuerzentrale für alle Musikmodule dient.
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2025 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

@echo off
REM Wechselt in das Verzeichnis der Batch-Datei
cd /d "%~dp0"

echo Starte Finjas Musik-Modul-Server...
python webserver.py

pause