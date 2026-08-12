# Onboard flow (dynamic — any future project)

Agents never maintain a list of all repos. Flow:

```
resolve(path)
  ├─ known → use effective_prefix + ERROR_CONTRACT.md
  └─ needs_onboard → ASK HUMAN → register → ensure → work
```

## Modes

| mode | codes look like | when |
|------|-----------------|------|
| `own_prefix` | `OMNI-502` | standalone brand |
| `inherit_parent` | `FINJA-502` | same system, separate folder |
| `module_under_parent` | `FINJA-502` + `module=omni` | child product on parent stack |

## Omni / VPet / Finja (illustrative only)

- Omni can be **Finja stack** (ecosystem=finja) and **VPet-owned** (owners=vpet).
- That is not a contradiction — register both tags.
- Choose mode with the human; do not assume.

## After register

Always `ensure` so missing `ERROR_CONTRACT.md` / contract JSON / AGENTS pointer appear automatically.
