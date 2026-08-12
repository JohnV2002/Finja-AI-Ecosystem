@echo off
@REM ======================================================================
@REM Project: J. Apps - AI-Coding Tooling
@REM Module: AI-Coding/error-contract / bin/error-contract.cmd
@REM Author: J. Apps (JohnV2002 / Sodakiller1)
@REM Version: 1.3.1
@REM Description: Repository-local Windows launcher for Error Contract.
@REM New in v1.0.0: Generic launcher without developer-specific paths.
@REM Copyright (c) 2026 J. Apps - Licensed under the MIT License.
@REM ======================================================================
@REM Prefer the installed ENGINE_ROOT; otherwise use this repository checkout.
setlocal
set "ERROR_CONTRACT_ENGINE="
if exist "%USERPROFILE%\.error_contract\ENGINE_ROOT.txt" (
  set /p ERROR_CONTRACT_ENGINE=<"%USERPROFILE%\.error_contract\ENGINE_ROOT.txt"
)
if not defined ERROR_CONTRACT_ENGINE (
  set "ERROR_CONTRACT_ENGINE=%~dp0.."
)
set "PYTHONPATH=%ERROR_CONTRACT_ENGINE%;%PYTHONPATH%"
python -m error_contract %*
exit /b %ERRORLEVEL%
