<!-- ERROR_CONTRACT_BEGIN -->
# Error Contract — ALWAYS ACTIVE (default coding rule)

Not a slash-command. Not optional. Applies whenever you **write or change code**
that can fail, catch, log, or report errors. Skip pure prose / no-code chat.

## Standing rule

For any code change that introduces, modifies, catches, logs, reports, propagates,
or otherwise touches an error path: **resolve the repository Error Contract first**.

Prefer the project's structured exception system over raw `print` / `console.log`,
generic exceptions, or catch-all fallback codes (`PREFIX-999`).

- If an appropriate dedicated code exists → **use it**
- If not → **create** one atomically (`error-contract create`) — do not silently abuse 999
- Do not introduce broad catches or raw error logging without an explicit technical reason

## Automatic preflight

Session hooks (Grok + **Codex**) run:

```
error-contract preflight .
```

Also written to: `.error_contract/ACTIVE.md` — read it. This ignored folder is
regenerated scanner state, not the namespace registry.

**Codex** injects SessionStart `additionalContext` into developer context.
**Grok** may not inject SessionStart stdout — still has rules + ACTIVE.md + Stop gate.

Know: project id, **prefix**, mode, parent/ecosystem, SoT path, KNOWN vs needs_onboard.

If `needs_onboard` → **ask the human** (own / inherit / module). Never invent a prefix.

## Automatic post-change verification

After meaningful code edits:

| Engine | Dirty tracking | Gate |
|--------|----------------|------|
| **Codex** | PostToolUse on `apply_patch` / Edit / Write | **Stop** `{decision:block, reason}` |
| **Grok** | PostToolUse on write tools | **Stop** block feedback |

Manual: `error-contract slap .` / `error-contract gate . --force`

Only **NEW** findings vs baseline on **edited files** fail (old debt is baseline).

## Completion checklist (code changes only)

1. Contract resolved / ACTIVE.md known
2. Relevant tests if present
3. Gate/slap clean for **new** issues
4. Honest report of remaining debt

No ceremony for one-line non-error edits.

## Engine

PATH: `error-contract …`  
ENGINE_ROOT: __ENGINE_ROOT__  
Registry: `%USERPROFILE%\.error_contract\projects.json`

Codex: trust hooks once via `/hooks`. Grok: `/hooks` reload or new session.
<!-- ERROR_CONTRACT_END -->
