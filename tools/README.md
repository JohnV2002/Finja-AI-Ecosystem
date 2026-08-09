# Finja dependency tooling

Local + CI helpers so Snyk / Dependabot / humans stop playing whack-a-mole with
forgotten imports and floating lower bounds.

## Quality control plane (why so many tools?)

Finja is a large, vibe-coded monorepo. The stack is intentional overkill so
shipping does not depend on rereading every line by hand:

| Layer | Tool |
|-------|------|
| Security / dataflow | CodeQL |
| Bugs / quality | SonarCloud |
| Supply chain | Trivy (+ Dependabot PRs) |
| IDE radar | Snyk (local) |
| Lint / multi-lang consistency | **MegaLinter v10** (`.mega-linter.yml`) |
| Behavior | Pytest + Codecov |
| Import / BOM hygiene | `dependency_guard.py` · `fix_bom.py` |

MegaLinter config: [`.mega-linter.yml`](../.mega-linter.yml) · workflow: [`.github/workflows/megalinter.yml`](../.github/workflows/megalinter.yml).

## 0. UTF-8 BOM fixer

A leading **UTF-8 BOM** (`ef bb bf`) breaks `ast.parse` and made the import
guard miss real imports (classic: `pygame` in `body/mouth.py`).

There was **no** older standalone “v1” BOM tool in this monorepo — only
`utf-8-sig` reads in a few places (Flare worker, dependency_guard).  
This script is the repo-wide fix + CI check.

```bash
python tools/fix_bom.py              # list offenders, exit 1 if any
python tools/fix_bom.py --fix        # strip BOM in place
python tools/fix_bom.py --check       # CI mode (same as default report)
python tools/fix_bom.py --ext py,md,yml
```

Wired into `.github/workflows/dependency-guard.yml` as **`--check`** before
the import scan.

## 1. Import guard (the important one)

GitHub Dependency Review watches **manifest** changes. It does **not** reliably
catch: `import foobar` without updating `requirements.txt`.

```bash
# from repo root
python tools/dependency_guard.py
python tools/dependency_guard.py --module finja-weather
python tools/dependency_guard.py --json deps-report.json
python tools/dependency_guard.py --strict   # also fail on unused pins
```

Legend:

| Mark | Meaning |
|------|---------|
| ✅ | used + declared in requirements / pyproject |
| ❌ | used third-party, **missing** from requirements |
| ⚠️ optional / test-only | e.g. pytest, yaml in docker-config tests |
| ⚠️ dynamic | optional / heavy (torch, playwright, …) |
| 📁 local | Finja / module-local code |
| 🗑️ | declared but no import found (noise possible) |

CI: `.github/workflows/dependency-guard.yml` runs this on push/PR to `main`.

## 2. Pinning & Snyk (the 0.01 vs 0.03 problem)

`package>=0.01` lets pip install `0.03` while the **file still allows** a
vulnerable floor. Prefer:

```text
package==0.03
```

or a tight range after review:

```text
package>=0.03,<0.04
```

If Snyk’s DB lags after a real fix, use a **time-boxed** ignore (do not silent-forever):

```powershell
snyk ignore `
  --id="SNYK-PYTHON-EXAMPLE-123456" `
  --expiry="2026-09-01" `
  --reason="Fixed in 0.03; advisory metadata not updated yet"
```

That writes into `.snyk` (policy). Commit it when intentional.

## 3. `requirements.in` + `pip-compile` (opt-in, not big-bang)

Per **active** module, when you are ready:

```text
# requirements.in  (human-edited direct deps only)
fastapi>=0.115,<1
cryptography>=43,<46
```

```bash
pip install pip-tools
pip-compile --resolver=backtracking path/to/requirements.in
# → writes path/to/requirements.txt with exact pins (+ transitive)
```

Repo helper:

```bash
python tools/compile_all_requirements.py           # all *.in
python tools/compile_all_requirements.py --upgrade
python tools/compile_all_requirements.py --check   # CI-friendly
```

**Why opt-in?** Blind pinning every module at once can break Docker images and
local “works on my machine” flows. Adopt module-by-module (start with Flare /
weather / scrapers — small surfaces).

Until a module has `requirements.in`, `compile_all_requirements.py` is a no-op
for that folder.

## 4. Dependabot

`.github/dependabot.yml` opens **PRs** (never silent main) for:

- each known `requirements.txt` directory
- GitHub Actions monthly

Group patch/minor Python updates by dependency name so you do not drown in PRs.
Your tests + Snyk should run on those PRs before merge.

## Suggested weekly ritual

1. Dependabot PRs → CI green → glance Snyk → merge  
2. Locally: `python tools/dependency_guard.py` after big import refactors  
3. When Snyk nags: bump pin / range, or expiry-bounded `snyk ignore`  
4. Optionally migrate one module to `requirements.in` + compile  

## Not covered (yet)

- Automatic README Open-Source table rewrite (can pipe `--json` later)
- Hash-pinning (`pip-compile --generate-hashes`) — enable when Docker install
  paths are ready for it
