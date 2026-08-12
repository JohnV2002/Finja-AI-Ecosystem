# ======================================================================
#                  GitHub Contract - Installer
# ======================================================================
#
#   Project: J. Apps - AI-Coding Tooling
#   Module:  github-contract / scripts
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.1.0
#   Description: Install skills, ALWAYS ACTIVE rules, hooks, PATH for
#                Grok / Codex / Claude (parity with error-contract).
#
#   New in 1.1.0:
#     - Installs the cross-project AI-Coding identity
#
#   New in 1.0.1:
#     - Version-aligned installer; installation behavior is unchanged
#
#   New in 1.0.0:
#     - Initial production installer
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License.
#
# ======================================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
Write-Host "Engine root: $Root" -ForegroundColor Cyan
if (Get-Command py -ErrorAction SilentlyContinue) {
  py -3 -m github_contract install-skills
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  python -m github_contract install-skills
} else {
  Write-Error "Python 3.10+ not found (py/python)."
}
Write-Host "Done. New terminal: github-contract --version" -ForegroundColor Green
Write-Host "Codex: codex -> /hooks -> trust GitHub Contract"
