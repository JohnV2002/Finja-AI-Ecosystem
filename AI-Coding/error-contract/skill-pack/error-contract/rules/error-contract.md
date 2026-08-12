# Error Contract — default coding policy (always on)

This is **repository policy**, not an optional skill. Do not wait for `/error-contract` or a user reminder.

## When it applies

Any change that **introduces, modifies, catches, logs, reports, propagates, or touches an error path**.

Skip for pure prose/chat with no code edits.

## Before coding (preflight)

If you have not resolved this repo yet this session:

1. Run `error-contract preflight .` (or `error-contract resolve .`)
2. Or read `.error_contract/ACTIVE.md` if present (written by SessionStart hook)

Know: **prefix**, **mode**, **parent/ecosystem**, **exceptions path**, **KNOWN vs needs_onboard**.

If `needs_onboard`: **ask the human** (own prefix vs parent vs module). Do not invent a prefix.
If `exempt`: do not onboard, scaffold, or run the automatic Error Contract gate.

## While coding

- Prefer the project's structured exception system (`AppError` / `PREFIX-xxx`) over:
  - `print(e)` / `console.log` / `console.error` as the error path
  - bare `except:` / empty catch / silent swallow
  - eternal generic `PREFIX-999` / catch-all when a dedicated code belongs
- If a dedicated code exists → use it
- If not → `error-contract propose --band …` and add the class; do not silently abuse 999

## Before saying "done"

If you changed code (especially error paths):

1. Preflight already done
2. Run project tests if they exist and are relevant
3. Run `error-contract gate .` or `error-contract slap .`
4. Fix **new** violations (baseline debt may exist; do not ignore *new* ones)
5. Report remaining findings honestly

Grok **Stop hook** may block completion when the gate finds new violations on edited files — treat that feedback as mandatory.

## Non-goals

Do not spam the user. Do not force ceremony on one-line harmless non-error edits. Fail soft outside code projects.
