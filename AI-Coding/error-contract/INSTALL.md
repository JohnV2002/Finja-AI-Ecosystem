# Error Contract v1.3.1 — Install Guide

**Project:** J. Apps - AI-Coding Tooling  
**Author:** J. Apps (JohnV2002 / Sodakiller1)  
**Version:** 1.3.1  

Install on any PC or laptop (Codex Desktop, Codex CLI, Grok).  
No private machine paths are baked into this package.

---

## Requirements

- Python **3.10+** (`python` or `py -3` on PATH)
- Optional: Codex CLI (for `/hooks` trust) + Codex Desktop
- Optional: Grok / Grok Build

---

## 1. Place the folder

Copy this package into your real git working tree (or clone after you publish).  
Example:

```text
<repo-path>\AI-Coding\error-contract
```

There is intentionally **no** `.git` inside some staging folders — use **your** VS / VS Code git workflow.

---

## 2. Install (skills + rules + hooks + PATH)

```powershell
cd <repo-path>\AI-Coding\error-contract
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
# or:
python -m error_contract install-skills
```

| Target | Purpose |
|--------|---------|
| `~\.grok\skills\error-contract\` | Grok skill |
| `~\.grok\AGENTS.md` + `~\.grok\rules\` | Always-on policy |
| `~\.grok\hooks\` | SessionStart / PostToolUse / Stop |
| `~\.codex\skills\error-contract\` | Codex skill |
| `~\.codex\AGENTS.md` | Always-on policy |
| `~\.codex\hooks.json` | Codex lifecycle hooks |
| PATH shim | `error-contract` command |
| `~\.error_contract\` | Engine root, project registry, **code ledger** |

### PATH check (new terminal)

```powershell
error-contract --version
# expect: error_contract 1.3.1
```

If missing:

```powershell
python -m error_contract install-path
# or temporarily:
$env:Path = "$env:USERPROFILE\.grok\bin;$env:USERPROFILE\.error_contract\bin;$env:Path"
```

---

## 3. Codex Desktop + CLI

`/hooks` is a **CLI** command (often **not** shown as a Desktop App menu item).

```powershell
cd D:\path\to\any\project
codex
```

Inside Codex:

```text
/hooks
```

Trust **Error Contract** hooks → quit CLI → **fully restart Codex Desktop** → **new thread**.

Ensure `~\.codex\config.toml` contains:

```toml
[features]
hooks = true
```

(`install-skills` adds this if missing.)

---

## 4. After updates (you replaced/copied a newer tree)

```powershell
cd <repo-path>\AI-Coding\error-contract
python -m error_contract install-skills
```

Then re-check `/hooks` if Codex says definitions changed, and start a **new** agent session.

Saying “hey, look at the folder” does **not** reinstall skills/hooks.

---

## 5. First Finja-style project (your paths)

```powershell
error-contract ledger-import --finja-core "D:\path\to\YOUR\core\exceptions.py"
error-contract seed-finja "D:\path\to\YOUR\FINJA CORE"
error-contract register "D:\path\to\finja-chat" `
  --id finja-chat --prefix FINJA `
  --mode module_under_parent --parent-id finja `
  --owners finja --ecosystem finja --module-default finja-chat --ensure
```

---

## 6. Daily

```text
error-contract preflight .
error-contract resolve .
error-contract slap .
error-contract gate . --force
error-contract ledger --prefix FINJA
error-contract reserve . --prefix FINJA --band session --owner finja-chat --module finja-chat --message "…"
```

---

License and support information live in the module [`README.md`](README.md).
