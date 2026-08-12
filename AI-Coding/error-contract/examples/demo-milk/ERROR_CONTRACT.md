# Error Contract (AI rules) — MILK

**DO NOT** invent ad-hoc logging (`print(e)`, `console.log(err)`, bare `except: pass`).
This project uses a structured exception system with branded codes `MILK-xxx`.

## Source of Truth
- Exceptions module: `core/exceptions.py`
- Contract JSON: `contracts/error_contract.json`
- Prefix: **MILK** (set at boot via `set_code_prefix("MILK")`)

## Rules for agents / contributors
1. New failures → raise an `AppError` subclass with the right band (1xx–11xx).
2. Recurring generic catches → **new dedicated code**, not eternal `MILK-999`.
3. Broad `except Exception` must wrap as `UnexpectedError` or map to a known code.
4. Never ship `console.log` / `print` as the error path.
5. Dashboard/inbox payload: `err.for_dashboard()` (code, module, context, cause).
6. Firewall codes 10xx/11xx: `to_inbox=False` by default.

## Bands
| Band | Range | Use |
|------|-------|-----|
| config | 100–199 | env, packages, config keys |
| llm | 200–299 | models, providers, timeouts |
| memory | 300–399 | stores, diary, corruption |
| session | 400–499 | auth, privileges |
| tool | 500–599 | tools/plugins |
| pipeline | 600–699 | guards, safety, input |
| host | 800–899 | system/maintenance |
| unexpected | 900–999 | last resort only |
| privacy | 1000–1099 | output firewall |
| injection | 1100–1199 | prompt injection |

## Commands
```
python -m error_contract scan .
python -m error_contract codes .
python -m error_contract propose . --band tool --message "steam api failed"
```
