#!/usr/bin/env sh
# ============================================================================
# Project: J. Apps - AI-Coding Tooling
# Module: AI-Coding/analytics-contract / scripts/install.sh
# Author: J. Apps (JohnV2002 / Sodakiller1)
# Version: 1.0.1
# Description: Install Analytics Contract and its agent skills on Unix systems.
# New in v1.0.0: Editable package and Codex/Grok/Claude skill installation.
# Copyright (c) 2026 J. Apps - Licensed under the MIT License.
# ============================================================================

set -eu
module_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$module_root"
python -m pip install -e .
python -m analytics_contract install-skills

