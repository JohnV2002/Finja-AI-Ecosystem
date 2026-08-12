#!/usr/bin/env bash
# ============================================================================
# Project: J. Apps - AI-Coding Tooling
# Module: AI-Coding/error-contract / scripts/install.sh
# Author: J. Apps (JohnV2002 / Sodakiller1)
# Version: 1.3.1
# Description: Installs Error Contract skills, hooks and the PATH wrapper.
# New in v1.0.0: Initial Linux and macOS installer for Codex and Grok.
# Copyright (c) 2026 J. Apps - Licensed under the MIT License.
# ============================================================================

# Install Error Contract (Linux/macOS): skills, AGENTS, hooks, PATH shim.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "Engine root: $ROOT"
python3 -m error_contract install-skills
echo ""
echo "Done. Open a new shell and run: error-contract --version"
echo "Codex: run 'codex' then '/hooks' and trust Error Contract hooks."
