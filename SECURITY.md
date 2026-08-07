# Security Policy

## Supported versions

This is a multi-module monorepo. Security fixes land on **`main`** for actively maintained modules (see the status table in [`README.md`](./README.md)).

Legacy / **Not Maintained** trees may not receive patches — prefer current modules.

## Reporting a vulnerability

**Please do not open a public GitHub Issue for security problems** (secrets, RCE, auth bypass, data leaks, etc.).

### Preferred (private)

1. Use GitHub **Private vulnerability reporting** on this repository  
   (Security tab → *Report a vulnerability*), **if enabled**.
2. Or email: **contact@jappshome.de**  
   Subject suggestion: `[SECURITY] Finja-AI-Ecosystem …`

### Please include (if you can)

- Affected module path (e.g. `finja-chat`, `finja-neural-network`, …)
- Description + impact
- Steps to reproduce / PoC (keep it minimal)
- Whether the issue is already public elsewhere
- Your preferred credit name (or anonymous)

### What to expect

- Acknowledgement when we see it (best effort — solo maintainer life)
- Fix or mitigation discussion privately when needed
- Public disclosure only after a fix (or coordinated timing)

## What is *out of* scope (usually)

- Issues that only affect **your** local misconfiguration (`.env` left world-readable on your VPS, etc.) — still fine to tip us if the **defaults in-repo** encourage that
- Vulnerabilities **only** in upstream dependencies already tracked by Snyk/Dependabot, unless we ship a known-bad pin and ignore it forever
- Social-engineering against stream chat (that’s stream moderation, not this repo)

## Hardening we already care about

- Dependency updates: Dependabot + `tools/dependency_guard.py` (see [`tools/README.md`](./tools/README.md))
- Snyk / SonarCloud where configured
- No secrets in git — use `.env` / host secrets; rotate if you ever paste a key in a PR

## Thanks

Responsible reports help keep Finja’s stack less cursed. 💖  
— J. Apps (JohnV2002 / Sodakiller1)
