# ============================================================================
# Project: J. Apps - AI-Coding Tooling
# Module: AI-Coding/analytics-contract / scripts/install.ps1
# Author: J. Apps (JohnV2002 / Sodakiller1)
# Version: 1.1.0
# Description: Install Analytics Contract and its agent skills on Windows.
# New in v1.0.0: Editable package and Codex/Grok/Claude skill installation.
# Copyright (c) 2026 J. Apps - Licensed under the MIT License.
# ============================================================================

$ErrorActionPreference = "Stop"
$moduleRoot = Split-Path -Parent $PSScriptRoot
Push-Location $moduleRoot
try {
    python -m pip install -e .
    python -m analytics_contract install-skills
}
finally {
    Pop-Location
}

