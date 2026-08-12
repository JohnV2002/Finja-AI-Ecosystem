# Error Contract - Ambient integration (Grok **and** Codex)

> Correction: Codex **does** have a full lifecycle hook system (stable `features.hooks`).
> Do not assume "Stop enforcement is Grok-only."

Verified against **Codex CLI `0.147.0-alpha.6.6`** on this machine + official hooks docs.

---

## Phase 1 - Root cause (still true)

| Layer | Limitation without hooks |
|-------|---------------------------|
| Skill | Opt-in by description / slash |
| AGENTS.md | Soft prose; easy to ignore mid-feature |
| PATH CLI | Works only if invoked |

Ambient = **rules + lifecycle hooks + baseline gate**, not memory alone.

---

## Capability matrix (honest)

| Capability | Grok (this install) | Codex 0.147 (`features.hooks=true`) |
|------------|---------------------|-------------------------------------|
| Global agent policy | `~/.grok/AGENTS.md` + `~/.grok/rules/` | `~/.codex/AGENTS.md` (+ project AGENTS.md) |
| Skill deep-dive | `~/.grok/skills/error-contract` | `~/.codex/skills/error-contract` |
| SessionStart preflight | Hook runs -> writes `.error_contract/ACTIVE.md` | Hook runs -> **also injects `additionalContext`** as developer context |
| SessionStart stdout -> model | **Often ignored** (docs: passive) | **Supported** (plain text or `hookSpecificOutput.additionalContext`) |
| Post-edit dirty tracking | PostToolUse on Write/Edit/search_replace | PostToolUse matcher `apply_patch\|Edit\|Write` (native edit path) |
| Stop gate / block finish | `{decision:block, reason}` | Same; **no `hookSpecificOutput` on Stop** (parse error if present) |
| Hook trust UI | `/hooks` enable/reload | `/hooks` **review & trust** required once per definition hash |
| Feature flag | always-on hooks dir | `[features] hooks = true` (default stable) |
| Non-code / TEMP | fail-soft skip | same runner |

### Codex-native details (do not Grok-copy blindly)

- Discovery: `~/.codex/hooks.json` and/or inline `[[hooks.*]]` in `config.toml`
- Events we use: **SessionStart**, **PostToolUse**, **Stop**
- PostToolUse file edits: tool is often **`apply_patch`** (matcher also accepts Edit|Write)
- `tool_input.command` for apply_patch holds the patch body -> we parse `*** Update File:` paths
- Field names on stdin: **snake_case** (`session_id`, `hook_event_name`, `tool_name`, `cwd`)
- Stop continues the agent with `reason` as continuation prompt text

### Grok-native details

- Discovery: `~/.grok/hooks/*.json`
- camelCase stdin (`sessionId`, `toolName`, ...)
- Strong extra: `~/.grok/rules/*.md` always scanned
- SessionStart context injection weaker than Codex

---

## Install

```powershell
cd path\to\error-contract
python -m error_contract install-skills
```

Creates/updates:

| Target | Purpose |
|--------|---------|
| `~/.codex/hooks.json` | Codex ambient EC hooks |
| `~/.codex/hooks/error-contract-hook.cmd` | PYTHONPATH launcher |
| `~/.codex/config.toml` | ensures `hooks = true` if missing |
| `~/.grok/hooks/error-contract.json` | Grok ambient EC hooks |
| `~/.grok/rules/error-contract.md` | Grok always-on rules |
| `~/.codex/AGENTS.md` + `~/.grok/AGENTS.md` | standing policy |

### After install (Codex)

1. Open Codex in a trusted project  
2. Run **`/hooks`**  
3. **Review & trust** the Error Contract hooks (required once; re-trust if definition changes)  
4. New session in Finja - do **not** mention Error Contract  

### After install (Grok)

1. New session or `/hooks` -> reload  
2. Rules load automatically  

---

## Runtime flow (both engines)

```
SessionStart -> preflight -> ACTIVE.md (+ Codex additionalContext)
PostToolUse (file edit) -> mark dirty + edited paths
Stop (turn end) -> if dirty -> gate (new findings vs baseline on edited files)
                 -> if NEW violations -> decision:block + reason
```

Baseline: first scan seeds `.error_contract/baseline.json` so old debt does not block every task.

---

## Tests performed (CLI / hook dry-run)

| Test | Result |
|------|--------|
| A Finja preflight | `status=known` `prefix=FINJA` |
| B gate after deliberate `print(e)` | exit 1 + Stop `decision:block` |
| C unknown repo | `needs_onboard` |
| D `%TEMP%` | skip not-a-code-project |
| Codex SessionStart shape (snake_case) | emits additionalContext JSON |
| Codex Stop shape | block JSON **without** hookSpecificOutput |

Fresh interactive Codex session still requires **one-time `/hooks` trust** - cannot be fully automated by policy (by design).

---

## Fresh-session checklist (you)

### Codex

1. `install-skills` already run  
2. `/hooks` -> trust EC hooks  
3. `cd` Finja Nervenzentrale -> new Codex chat  
4. Ask a normal coding task (no EC mention) -> expect preflight context / ACTIVE.md  
5. Introduce raw `print(e)` -> expect Stop continuation with gate text  

### Grok

1. New session in Finja  
2. Same regression -> Stop block  

---

## What we still do **not** claim

- Codex Desktop vs CLI may differ slightly in hook UI; this targets **CLI + IDE using `~/.codex`**.  
- Hosted tools (e.g. WebSearch) do not hit local PostToolUse.  
- Full interactive "agent ignored me" proof needs a human-watched Codex session after trust.  

**Bottom line:** Stop enforcement and SessionStart injection are **native on Codex** when hooks are enabled + trusted. Grok remains strong on rules injection; Codex is actually **stronger on SessionStart context injection**.

---

## Global code ledger (anti FINJA-820 split-brain)

Storage: `%USERPROFILE%\.error_contract\code_ledger.json`

| Concept | Meaning |
|---------|---------|
| **Prefix** | Number space. `AST-820` â‰  `FINJA-820`. Finja never consumes AST codes. |
| **code_num under prefix** | **World-unique**. Only one meaning for `FINJA-820` across core, chat, plugins. |
| **Owner** | Who reserved it (`finja`, `finja-chat`, `obs-bridge`, ...) |
| **source_path** | Where the class lives (optional). Empty = ledger-only claim. |
| **Not required** | Dumping every code into `core/exceptions.py` |

```powershell
# Bootstrap Finja core numbers once
error-contract ledger-import --finja-core

# Chat Twitch error - ledger only OR module-local file
error-contract reserve . --prefix FINJA --band session --owner finja-chat --module finja-chat --message "twitch oauth invalid"
error-contract add-code . --prefix FINJA --band session --owner finja-chat --module finja-chat `
  --message "twitch oauth invalid" --target "path\to\chat\errors.py"

# OBS - Finja core does not need this class file
error-contract reserve . --prefix FINJA --band tool --owner obs-bridge --module obs `
  --message "obs websocket down" --target "obs_errors.py"

# Asteroid = other prefix, own space
error-contract reserve . --prefix AST --band host --owner asteroid --message "level load fail"

error-contract ledger --prefix FINJA
```

`propose` consults the ledger so free slots skip numbers already taken by other owners.

---

License and support information live in the module [`README.md`](README.md).

