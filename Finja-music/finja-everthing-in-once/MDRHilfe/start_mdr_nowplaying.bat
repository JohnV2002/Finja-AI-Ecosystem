@echo off
REM ======================================================================
REM             Finja's Brain & Knowledge Core - MDR Starter
REM ======================================================================
REM
REM   Project: Finja - Twitch Interactivity Suite
REM   Author: JohnV2002 (J. Apps / Sodakiller1)
REM   Version: 1.0.0 (MDR Modul)
REM
REM   Description: Startet den Python-Crawler (mdr_nowplaying.py), der den
REM                aktuell gespielten Song von MDR Sachsen-Anhalt abruft.
REM
REM ----------------------------------------------------------------------
REM  Features:
REM ----------------------------------------------------------------------
REM   • Startet das MDR "Get Content" Modul mit einem Doppelklick.
REM   • Sucht automatisch nach der installierten Python-Version (py, python, etc.).
REM   • Prüft, ob die benötigten Python-Pakete (requests, defusedxml) vorhanden
REM     sind und installiert sie bei Bedarf automatisch nach.
REM   • Stellt sicher, dass die Konsole für die Log-Ausgaben geöffnet bleibt.
REM
REM ----------------------------------------------------------------------
REM
REM   Copyright (c) 2025 J. Apps
REM   Licensed under the MIT License.
REM
REM ======================================================================

setlocal ENABLEDELAYEDEXPANSION
title MDR NowPlaying Starter
chcp 65001 >nul
cd /d "%~dp0"

echo(
echo ==============================
echo   MDR NowPlaying – Starter
echo ==============================
echo  Ordner: %CD%
echo(

REM (Der Rest deines Skripts folgt hier...)

@echo off
setlocal ENABLEDELAYEDEXPANSION
title MDR NowPlaying Starter
chcp 65001 >nul
cd /d "%~dp0"

echo(
echo ==============================
echo   MDR NowPlaying – Starter
echo ==============================
echo  Ordner: %CD%
echo(

REM -------------------------------
REM  (OPTIONAL) Region/URLs anpassen
REM  -> auskommentieren und nach Bedarf setzen
REM set MDR_XML_URL=https://www.mdr.de/XML/titellisten/mdr1_sa_2.xml  
REM set MDR_STREAM_URL=https://mdr-284290-1.sslcast.mdr.de/mdr/284290/1/mp3/high/stream.mp3  
REM set MDR_HTML_URL=https://www.mdr.de/mdr-sachsen-anhalt/titelliste-mdr-sachsen-anhalt--102.html  
REM set MDR_POLL_S=10
REM -------------------------------

REM ---- Python finden (py -3, py, python, python3) ----
set "PYCMD="
call :trycmd "py -3" && set "PYCMD=py -3"
if not defined PYCMD call :trycmd "py"      && set "PYCMD=py"
if not defined PYCMD call :trycmd "python"  && set "PYCMD=python"
if not defined PYCMD call :trycmd "python3" && set "PYCMD=python3"

if not defined PYCMD (
  echo [ERR] Python nicht gefunden. Bitte installieren und PATH setzen.
  echo       Download: https://www.python.org/downloads/  
  echo       Tipp: Haken bei "Add Python to PATH" setzen.
  echo(
  pause
  exit /b 1
)

for /f "tokens=2,*" %%a in ('%PYCMD% -V 2^>^&1') do set "PYVER=%%a"
echo [i] Python: %PYCMD%  (Version %PYVER%)
echo(

REM ---- Dependencies still & leise installieren ----
echo [i] Pruefe/Installiere Abhaengigkeiten...
%PYCMD% -m pip show requests    >nul 2>&1 || %PYCMD% -m pip install --user -q requests
%PYCMD% -m pip show defusedxml  >nul 2>&1 || %PYCMD% -m pip install --user -q defusedxml
REM BeautifulSoup wird fuer die reine XML-Variante nicht benoetigt;
REM falls du HTML-Fallback nutzt, kannst du die naechste Zeile aktivieren:
REM %PYCMD% -m pip show beautifulsoup4 >nul 2>&1 || %PYCMD% -m pip install --user -q beautifulsoup4
echo [i] OK.
echo(

echo [i] Starte MDR NowPlaying...
echo [i] Ausgabe: nowplaying.txt  ^|  Quelle: now_source.txt
echo(

REM ---- Script starten (Logs unbuffered) ----
%PYCMD% -u mdr_nowplaying.py --out nowplaying.txt
set "RC=%ERRORLEVEL%"

echo(
echo [i] Script beendet. Exit-Code: %RC%
echo     (Fenster offen lassen zum Lesen der Logs.)
echo(
pause >nul
exit /b %RC%

:trycmd
REM prueft ob ein Python-Kommando laeuft (Version ausgeben)
%~1 -V >nul 2>&1
exit /b %ERRORLEVEL%