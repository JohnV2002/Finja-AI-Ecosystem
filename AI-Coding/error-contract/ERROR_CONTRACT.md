# Error Contract v1.3.1 — Standing Rules

**Project:** J. Apps - AI-Coding Tooling  
**Version:** 1.3.1  

> Goal: projects do not end in `print(e)` / bare catch-alls.  
> Same engine; project-specific prefixes; **global unique numbers per prefix**.

## For AI agents (always-on policy)

1. `error-contract resolve PROJECT` first  
   - `known` → use effective prefix  
   - `needs_onboard` → **ask the human**, then `register`
2. No `print(e)` / `console.log` / bare `except: pass` as the product error path  
3. Do not invent a second exception system  
4. New failures → structured `AppError` (or project equivalent), bands 1xx–11xx  
5. Recurring catch-alls → `reserve` / `propose --reserve`, not eternal `PREFIX-999`  
6. Missing docs → `ensure`  
7. Numbers: consult the repo-root **`error_contract.json` legend** so `FINJA-820` cannot mean two things  

### Placement

- **Prefix** = brand space (`FINJA` vs `AST`)  
- **Owner** = who owns a number (`finja`, `finja-chat`, `obs-bridge`)  
- **Class file** may be module-local — not everything belongs in Finja `core/exceptions.py`  

### Modes

| mode | codes | use |
|------|-------|-----|
| `own_prefix` | `OMNI-xxx` | own brand |
| `inherit_parent` | parent codes | same system, other folder |
| `module_under_parent` | parent codes + `module=` | e.g. Finja stack, chat module |

## CLI

```bash
python -m error_contract install-skills
error-contract preflight .
error-contract resolve .
error-contract slap .
error-contract ledger --prefix FINJA
error-contract create . TwitchOauthInvalidError --band session --message "..."
error-contract category . brand_new_things --prefix FINJA --range 1400-1499 --description "..."
error-contract add-code . --prefix FINJA --band tool --owner obs-bridge --module obs --target obs_errors.py --message "…"
```

Project registration and fallback ledger (per machine):

- `%USERPROFILE%\.error_contract\projects.json`  
- `%USERPROFILE%\.error_contract\code_ledger.json`  

Canonical public error legend (repo-backed, path-neutral):

- `<repository-root>/error_contract.json`

License and support information live in the module [`README.md`](README.md).
