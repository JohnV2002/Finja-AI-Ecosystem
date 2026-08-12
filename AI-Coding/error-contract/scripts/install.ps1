# ============================================================================
# Project: J. Apps - AI-Coding Tooling
# Module: AI-Coding/error-contract / scripts/install.ps1
# Author: J. Apps (JohnV2002 / Sodakiller1)
# Version: 1.3.2
# Description: Installs Error Contract skills, hooks and the PATH wrapper.
# New in v1.0.0: Initial Windows installer for Codex and Grok.
# Copyright (c) 2026 J. Apps - Licensed under the MIT License.
# ============================================================================

# Install Error Contract on this Windows machine (Grok + Codex + PATH).
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "Engine root: $Root" -ForegroundColor Cyan

$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
  $py = "py"
  $pyArgs = @("-3", "-m", "error_contract", "install-skills")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $py = "python"
  $pyArgs = @("-m", "error_contract", "install-skills")
} else {
  Write-Error "Python 3.10+ not found on PATH (need 'py' or 'python')."
}

& $py @pyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1) Open a NEW terminal and run:  error-contract --version"
Write-Host "  2) Codex CLI:  codex  then  /hooks  and trust Error Contract hooks"
Write-Host "  3) Restart Codex Desktop; new Grok session"
Write-Host "  4) Docs: INSTALL.md"
