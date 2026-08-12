# 🛡️ GitHub Contract v1.1.0

*Your code goes public without taking your PC with it.*

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](../../README.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../../LICENSE)

GitHub Contract is a **cross-project local AI-coding plugin** built for the
J. Apps workflow. It keeps every public module recognizably part of its actual
project: complete ecosystem headers, one honest module version, a proper README
and absolutely no private paths or secrets slipping into GitHub.

It runs for Codex and Grok through ambient lifecycle hooks, and it can also be
used directly as a CLI. The scanner checks the files; the installed skill tells
the coding agent how to fix them without flattening Finja's personality.

---

## ✨ What It Protects

- **Ecosystem headers everywhere:** Python, HTML, JavaScript, TypeScript, CSS,
  PowerShell, Batch, Shell, PHP, C/C++, YAML, TOML, SVG, Dockerfiles and more.
- **One module version:** Every source header and package manifest agrees on
  `MAJOR.FEATURES.BUGS`.
- **Per-file history:** Each file may describe its own `New in` changes while
  still sharing the module version.
- **No private machine leaks:** Absolute Windows/macOS/Linux user paths, UNC
  shares, private LAN addresses, tokens and connection strings are flagged.
- **Finja HTML is understood:** Existing `<!-- ... -->` ecosystem banners are
  first-class headers, including Finja's established author format.
- **Agent guardrails:** Session preflight and stop hooks keep the policy active
  without relying on someone remembering a prompt.

---

## 🧠 The Contract

Every commentable source file in a covered project carries:

```text
Actual project · Module · Author · Version · Description · New in
Copyright (c) J. Apps · MIT License
```

The syntax follows the file type:

| File type | Header style |
|-----------|--------------|
| Python | Module docstring (`""" ... """`) |
| HTML / SVG | HTML comment (`<!-- ... -->`) |
| Batch / CMD | `@REM` banner |
| Shell / PowerShell / YAML / TOML | `#` comment banner |
| JavaScript / TypeScript / CSS / C-family | Block or line comments |

JSON and other formats that cannot legally contain comments are not forced to
carry an invalid header. Their package version is still checked where
applicable.

---

## 🚀 Install

From the plugin folder:

```powershell
cd <repo-path>\AI-Coding\github-contract
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

Or install directly through Python:

```powershell
python -m github_contract install-skills
```

Open a new terminal and verify it:

```powershell
github-contract --version
```

Codex users review and trust the hook once with `/hooks`, then restart Codex
Desktop and open a new task. Grok users start a new session or reload hooks.

The complete setup and update flow lives in [`INSTALL.md`](INSTALL.md).

---

## 💻 Daily Commands

```text
github-contract detect .
github-contract preflight .
github-contract scan . --version 1.1.0
github-contract check-version . --version 1.1.0
```

Generate a header when a new file joins a module:

```text
github-contract header --kind html --version 1.1.0 \
  --project "Finja - Twitch Interactivity Suite" \
  --title "Finja Overlay" --module "finja-chat / overlay.html" \
  --description "OBS browser source"
```

The scan returns findings with file, line, severity and a concrete repair hint.
It must be run from the module root so version boundaries stay meaningful.

---

## 📁 Project Structure

| Path | Purpose |
|------|---------|
| `github_contract/` | Detection, scanning, headers, CLI and lifecycle hooks |
| `skill-pack/` | Installed skill and always-active agent policy |
| `scripts/` | Windows and Unix installers |
| `test_scanner.py` | Regression tests for headers and leak detection |

Machine-specific installation state belongs in `~/.github_contract/`, never in
the public repository.

---

## 📋 Version History

### v1.1.0

- Separated the plugin's AI-Coding identity from the target project's identity.
- Added `--project` so generated headers name the real project or suite.
- Replaced the Finja-specific generator default with neutral `J. Apps Project`.

### v1.0.1

- Fixed absolute drive paths in Markdown escaping the leak scanner.
- Fixed public `/users/` API URLs being reported as private home directories.
- Added regression coverage for Finja's existing HTML banners.
- Ignored generated `.error_contract` and `.github_contract` state.
- Expanded header coverage to the source and configuration types used by Finja.
- Removed the duplicate module license and private installation path.

### v1.0.0

- Added module detection, header generation and version-unity checks.
- Added secret/private-path scanning and README validation.
- Added Codex and Grok skills, lifecycle hooks and local CLI installation.

---

## 📜 License

**MIT** © 2024–2026 J. Apps — this module uses the repository root
[`LICENSE`](../../LICENSE). No duplicate license copy is kept here.

## 🆘 Support & Contact

- **Email:** contact@jappshome.de
- **Website:** [jappshome.de](https://jappshome.de)
- **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)
