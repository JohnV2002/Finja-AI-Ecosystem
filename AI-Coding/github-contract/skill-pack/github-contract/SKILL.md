---
name: github-contract
description: >
  J. Apps GitHub / production contract: mandatory ecosystem headers, one module-wide
  version MAJOR.FEATURES.BUGS (changelog may differ per file), README License+Support,
  no secret/path leaks. Use whenever working in a git repo, GitHub public module,
  Finja-AI-Ecosystem package, or when user mentions headers, version bump, SemVer,
  production, no leak, /github-contract. Always-on via AGENTS.md — not optional.
metadata:
  short-description: "Headers + module SemVer + no-leak for GitHub"
---

# GitHub Contract

## When this applies

If the workspace is **git**, has a **GitHub** remote / `.github`, belongs to the
J. Apps workflow, or the user is preparing a **public/production** module — this
contract is **mandatory**.

## Version scheme (always)

```
MAJOR . FEATURES . BUGS
  1   .    0     .  0
```

| Segment | Meaning |
|---------|---------|
| **MAJOR** | Breaking / big identity change |
| **FEATURES** | New features (not bugs) |
| **BUGS** | Fixes / patches only |

- **Same version string in EVERY file of the module** (headers + pyproject/package).
- **Changelog / "New in" bullets may differ per file.**

## Required file header

Match the target project's established ecosystem style (for example
`finja-weather` or `finja-chat`):

- Project: the actual project/suite label — never the Contract plugin itself
- Module: `module-name / file`
- Author: `J. Apps (JohnV2002 / Sodakiller1)`
- Version: **module version**
- Description + **New in vX.Y.Z** (file-specific)
- Copyright MIT (c) 2026 J. Apps
- Website / Support when using the full banner (Python services)

Syntax: `"""` Python · `@REM` Batch · `<!-- -->` HTML/SVG · native comment
syntax for CSS, JS/TS, Shell, PowerShell, C-family, YAML and TOML. Never make
JSON invalid just to force a comment into it.

Generate:

```text
github-contract header --kind py --version 1.0.0 --project "Finja - Twitch Interactivity Suite" --title "..." --module "..." --description "..."
```

## No leaks

Never commit: API keys, oauth tokens, private keys, connection strings, absolute
drive/user paths, UNC/NAS paths, LAN IPs or real `.env` values. Use
`<repo-path>`, `private/`, environment variables and `*.example` files.

## README

Public modules need version in the title, what/why, and one License section that
links the applicable repository-root license. Do not copy the full license into
the module or create a second `LICENSE` when the root license already covers it.

```markdown
## License
**MIT** (c) J. Apps — full text: repository root
[`LICENSE`](<relative-path-to-root-license>).

## Support & Contact
- Email: contact@jappshome.de
- Website: jappshome.de
- Support: buymeacoffee.com/J.Apps
```

## CLI

```text
github-contract detect .
github-contract preflight .
github-contract scan . --version X.Y.Z
github-contract check-version . --version X.Y.Z
```

ENGINE_ROOT: see `ENGINE_ROOT.txt` next to this skill.
