---
name: error-contract
description: >
  Cross-project structured error contract (Finja-compatible). Dynamic registry
  of project prefixes — never invent print/console.log/999 catch-alls. ALWAYS
  relevant when writing or editing any code (features, tools, games, APIs), not
  only when the user says "errors". Use for exceptions, try/catch, logging,
  scaffolding, ERROR_CONTRACT, FINJA/OMNI codes, slap, onboard, Omni/VPet,
  /error-contract, or "kein console.log". Standing global rules live in
  AGENTS.md/CLAUDE.md — this skill is the deep-dive procedure.
metadata:
  short-description: "Structured errors (always-on via AGENTS.md)"
---

# Error Contract

> **Always-on:** Global `AGENTS.md` / `CLAUDE.md` already inject the standing rules
> every session. You do **not** need `/error-contract` for them to apply.
> This skill is the full procedure when onboarding or debugging the contract.

## Hard rules

1. **No** `print(e)`, `console.log(err)`, bare `except: pass` as the error path.
2. **No** inventing a second exception system if one exists.
3. **No** hard-coded list of all user projects. Use the **dynamic registry**.
4. New/unknown repo → **stop and ask** (onboard). Do not guess OMNI vs FINJA.

## Engine location

Read `ENGINE_ROOT.txt` next to this skill (absolute path). Then:

```text
cd <ENGINE_ROOT>
python -m error_contract <command> <project-path>
```

If missing: `python -m error_contract` from `finja - exception Plugins` workspace, or
`%USERPROFILE%\.error_contract\ENGINE_ROOT.txt`.

## Always first: resolve

```bash
python -m error_contract resolve "PROJECT_PATH"
```

| status | action |
|--------|--------|
| `known` | Use `effective_prefix`. Read root `error_contract.json`; read `ERROR_CONTRACT.md` only if the repo intentionally has one. |
| `exempt` | Contract tooling opted out in `pyproject.toml`; do not onboard, scaffold or invent a prefix. |
| `needs_onboard` | **Ask the human** the questions from the CLI output. Do not scaffold yet. |

### Onboard questions (ask human — Omni example)

Unknown project (e.g. **Omni**):

1. **Mode**
   - `own_prefix` → e.g. `OMNI-xxx` (own brand)
   - `inherit_parent` → same codes as parent (e.g. `FINJA-xxx`)
   - `module_under_parent` → parent codes + default `module=omni` (Finja stack, VPet world)
2. **Prefix** (if own) or **parent id** (if inherit/module)
3. **owners** (e.g. `vpet`) and **ecosystem** (e.g. `finja`) — both can apply
4. Confirm; then register

Example Omni as Finja-codes under VPet ownership:

```bash
python -m error_contract register "PATH\omni" --id omni --prefix FINJA \
  --mode module_under_parent --parent-id finja \
  --owners vpet --ecosystem finja --module-default omni --ensure --scaffold
```

Example Omni as own brand:

```bash
python -m error_contract register "PATH\omni" --id omni --prefix OMNI \
  --mode own_prefix --owners vpet --ecosystem finja --ensure --scaffold
```

## After known

```bash
python -m error_contract ensure "PROJECT_PATH"          # auto-docs if missing
python -m error_contract ensure "PROJECT_PATH" --scaffold   # + exceptions.py
python -m error_contract codes "PROJECT_PATH"
python -m error_contract slap "PROJECT_PATH"
python -m error_contract propose "PROJECT_PATH" --band tool --message "..."
python -m error_contract create "PROJECT_PATH" ToolFailureError --band tool --message "..."
python -m error_contract category "PROJECT_PATH" future_features --range 1400-1499 --description "..."
```

## Coding contract

- Raise `AppError` subclasses in a category defined by the namespace's public
  legend. The traditional Finja taxonomy starts at 1xx but is not a hard ceiling.
- New families such as 1400-1499 are added with `error-contract category`; the
  engine must not invent their meaning or impose a fixed maximum.
- Recurring catch-all → `propose` new code, do not eternal `PREFIX-999`.
- Dashboard payload: `err.for_dashboard()`; firewall 10xx/11xx usually `to_inbox=False`.
- `module_under_parent`: pass `module=<module_default>` when raising.
- A repository has one public root `error_contract.json`. It may contain several
  namespaces; local `exceptions.py`
  files implement only the codes their module actually uses.
- Create a code atomically with `error-contract create`; do not hand-edit a
  local manifest and registry independently.

## Install / refresh skills

```bash
python -m error_contract install-skills
python -m error_contract seed-finja
```

## Registry storage

User-global (grows with all 80+ projects, no repo edit required):

`%USERPROFILE%\.error_contract\projects.json`

List: `python -m error_contract projects`

Canonical error-code legend (repo-backed, no machine paths):

`<TARGET_REPOSITORY_ROOT>/error_contract.json`

Project-local `.error_contract/` is ignored scanner cache. `baseline.json`
contains pre-existing finding fingerprints so only new debt blocks the gate.

