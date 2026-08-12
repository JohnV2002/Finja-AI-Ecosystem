#!/usr/bin/env bash
# ======================================================================
#                  GitHub Contract - Installer
# ======================================================================
#
#   Project: J. Apps - AI-Coding Tooling
#   Module:  github-contract / scripts
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.1.1
#   Description: Install skills/hooks/PATH (Linux/macOS).
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
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m github_contract install-skills
echo "Done. github-contract --version"
