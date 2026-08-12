# 🛡️ GitHub Contract v1.1.0 — Install Guide

**Project:** J. Apps - AI-Coding Tooling  
**Module:** AI-Coding / github-contract  
**Author:** J. Apps (JohnV2002 / Sodakiller1)  
**Version:** 1.1.0  

Install on any machine using the same local agent pattern as Error Contract.
No developer-specific path is required or stored in this repository.

## Requirements

- Python 3.10+
- Optional: Codex CLI, Grok or Claude

## Install

Open the plugin directory through your own checkout:

```powershell
cd <repo-path>\AI-Coding\github-contract
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

Or:

```powershell
python -m github_contract install-skills
```

## Verify

Open a new terminal:

```powershell
github-contract --version
# github_contract 1.1.0
```

## Codex

1. Start the Codex CLI inside a trusted project.
2. Run `/hooks` and review **GitHub Contract**.
3. Trust the hook, restart Codex Desktop and open a new task.

## Grok

Start a new session or reload hooks. The installed standing rule lives in the
local Grok configuration directory.

## After Updates

From the plugin folder:

```powershell
python -m github_contract install-skills
```

Re-review `/hooks` if Codex reports that the hook definition changed.

## Daily Check

```text
github-contract detect .
github-contract scan . --version 1.1.0
```

License and support information live in the module [`README.md`](README.md).
