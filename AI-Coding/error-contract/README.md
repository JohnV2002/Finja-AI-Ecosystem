# Error Contract v1.3.2

*If it can fail, it gets a real name.*

[![Version](https://img.shields.io/badge/version-1.3.2-blue.svg)](../../README.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../../LICENSE)

Error Contract is a **cross-project local AI-coding plugin** built for the
J. Apps workflow. It keeps Codex, Grok and Claude from turning error paths into
a pile of `print(e)`, swallowed exceptions and mystery `999` fallbacks.

It detects the project it is working in, resolves the correct error namespace,
checks changed files and blocks new violations before an agent calls the job
finished. Finja uses `FINJA-xxx`; unrelated projects can keep their own prefix
without polluting Finja's number space.

---

## ✨ What It Does

- **Knows the project:** Resolves the right prefix, owner, parent and module from
  a dynamic registry instead of a hard-coded folder list.
- **Keeps codes unique:** A public repo-root `error_contract.json` prevents one
  `FINJA-820` from meaning three different things in core, chat and OBS.
- **Catches lazy error paths:** Finds swallowed exceptions, raw error printing,
  broad catches and overused generic fallback codes.
- **Guards agent edits:** Session, post-edit and stop hooks make the contract
  ambient for Codex and Grok.
- **Respects existing systems:** It detects a project's own exception classes
  and extends them instead of inventing a second framework.
- **Stays private:** Machine state remains local; canonical shared namespaces
  contain only logical project paths and no machine-specific locations.

---

## 🧠 How It Fits Together

```text
agent starts in a project
        ↓
resolve project → prefix + ownership + source of truth
        ↓
agent edits code → remember changed files
        ↓
stop gate → scan only new findings against the baseline
        ↓
clean: finish     violation: block and explain
```

The package has three parts:

| Part | Job |
|------|-----|
| **CLI engine** | Detects projects, scans code, manages the registry and reserves codes. |
| **Agent skill** | Teaches Codex, Grok and Claude how to follow the contract correctly. |
| **Lifecycle hooks** | Run preflight and the baseline-aware stop gate automatically. |

This is a development guardrail, not a replacement for Finja's runtime error
inbox or dashboard.

---

## 🚀 Install

From this folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

Or install through Python:

```powershell
python -m error_contract install-skills
```

Then open a new terminal and check the command:

```powershell
error-contract --version
```

Codex users must review and trust the installed hooks once with `/hooks`, then
restart Codex Desktop and open a new task. Grok users only need a fresh session
or a hook reload.

For the complete multi-machine setup and update flow, see
[`INSTALL.md`](INSTALL.md).

---

## 💻 Daily Commands

```text
error-contract preflight .
error-contract resolve .
error-contract slap .
error-contract gate . --force
error-contract projects
```

Register a project only after its ownership and prefix are confirmed:

```text
error-contract register PATH --id PROJECT --prefix FINJA \
  --mode own_prefix|inherit_parent|module_under_parent
```

Reserve or add a dedicated code instead of teaching `999` another unrelated
meaning:

```text
error-contract propose . --band tool --message "what failed" --reserve
error-contract create . TwitchOauthInvalidError --band session \
  --message "Twitch OAuth is invalid"
```

Number ranges are data, not a hard ceiling in the engine. A repository can add
a future category at any range and immediately create codes in it:

```text
error-contract category . brand_new_things --prefix FINJA \
  --range 1400-1499 --description "Entirely new feature family"
error-contract create . CompletelyNewThingError \
  --band brand_new_things --message "The new subsystem failed"
```

---

## 🧩 Prefixes, Owners and Modules

| Concept | Meaning |
|---------|---------|
| **Prefix** | The brand's number space, such as `FINJA` or `AST`. |
| **Code** | A globally unique number inside one prefix. |
| **Owner** | The project or component that reserved the code. |
| **Module** | The runtime tag, for example `finja-chat` or `obs`. |
| **Class file** | Where the exception lives; it may stay module-local. |

Finja Chat can therefore use `FINJA-xxx` with `module=finja-chat`, while an
unrelated game keeps `AST-xxx`. Not every exception class has to move into
Finja core.

---

## 📁 Project Structure

| Path | Purpose |
|------|---------|
| `error_contract/` | Python engine and CLI |
| `skill-pack/` | Skills and standing rules installed for coding agents |
| `hooks/` | Codex and Grok lifecycle hook definitions |
| `<repo>/error_contract.json` | Public legend containing every namespace, owner and code |
| `examples/` | Safe demo projects for onboarding and scaffolding |
| `scripts/` | Windows and Unix installers |
| [`ERROR_CONTRACT.md`](ERROR_CONTRACT.md) | Short standing rules for humans and agents |
| [`AMBIENT.md`](AMBIENT.md) | Hook architecture, capabilities and limitations |

Project-local `.error_contract/` contains regenerated preflight state. Its
`baseline.json` stores fingerprints of existing scanner findings so only new
debt blocks completion. The folder is not a registry and must remain ignored.
The user-level `~/.error_contract/` contains project registration and legacy
fallback ledgers; neither location belongs in a public commit.

Contract tooling can explicitly opt out of recursive Error Contract onboarding
with `[tool.error-contract] exempt = true` in `pyproject.toml`. Exempt projects
do not receive an error namespace, local state folder or automatic stop gate.

---

## 📋 Version History

### v1.3.2

- Added an explicit, project-local exemption for contract tooling.
- Made resolve, preflight and the automatic gate skip exempt projects cleanly.
- Prevented Error Contract and GitHub Contract from recursively onboarding one another.

### v1.3.1

- Stopped generating repetitive `ERROR_CONTRACT.md` files in every submodule.
- Defined the root JSON legend as mandatory and Markdown guidance as optional.

### v1.3.0

- Made numeric categories dynamic and owned by each namespace in the root legend.
- Added `error-contract category` for future ranges such as `1400-1499`.
- Removed the engine-level numeric ceiling for project-defined categories.

### v1.2.0

- Moved the canonical code legend to public `<repository-root>/error_contract.json`.
- Added multi-namespace legends so monorepos can document FINJA, MILK, AST and others together.
- Made scaffolding create and maintain the public root legend automatically.
- Renamed local implementation indexes to `contracts/error_contract.module.json`.

### v1.1.0

- Added a canonical namespace registry as the shared code Grundbuch.
- Replaced copied per-module taxonomies with small local implementation manifests.
- Added atomic `error-contract create` for registry reservation plus local class creation.
- Removed absolute paths from generated manifests, baselines and preflight briefs.
- Made local AGENTS/CLAUDE pointer files opt-in.

### v1.0.0

- Added cross-project detection, resolution, scanning and scaffolding.
- Added dynamic project ownership and parent inheritance.
- Added the prefix-wide code ledger with module-local exception support.
- Added Codex and Grok lifecycle hooks with a baseline-aware stop gate.
- Added agent skill installation and a local PATH wrapper.

---

## 📜 License

**MIT** © 2024–2026 J. Apps — this module uses the repository root
[`LICENSE`](../../LICENSE). No second license copy is kept here.

## 🆘 Support & Contact

- **Email:** contact@jappshome.de
- **Website:** [jappshome.de](https://jappshome.de)
- **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)
