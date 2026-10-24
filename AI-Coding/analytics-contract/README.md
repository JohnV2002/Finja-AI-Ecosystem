# 📊 Analytics Contract v1.0.1

*Observe every project. Depend on nothing.*

[![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)](../../README.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../../LICENSE)

Analytics Contract is the language-neutral analytics foundation for J. Apps
projects. It recognizes the project, its Error Contract inbox, its runtimes and
the measurements that are actually useful. It then gives Codex, Grok and Claude
one stable contract for adding analytics while code is built or migrated.

Analytics is **off by default**. A project must start and work normally when no
collector exists, its endpoint is unavailable, or analytics remains disabled.

## Foundation

```text
project detection
        ↓
Error Contract / inbox detection
        ↓
analytics_contract.json (enabled=false)
        ↓
project-specific metric plan
        ↓
language-native instrumentation using one shared event envelope
        ↓
optional collector and future AI adapter
```

There is no legacy debt baseline. The contract is the target state: existing
projects receive a migration plan, while new and substantially changed runtime
code receives relevant instrumentation immediately.

## What It Detects

- Programming languages and project identity
- Error Contract and Error Inbox integration
- Docker/container workloads and CPU, memory, restart needs
- Web/API traffic and loading times
- Render loops, FPS and frame duration
- Workers, jobs and queue depth
- Database operation outcomes and duration
- AI/model request outcomes and latency

It does not instrument every function. It selects meaningful user, API, job,
pipeline, external-service and rendering boundaries.

## Safe Runtime Contract

- `analytics.enabled` defaults to `false`.
- Disabled means no endpoint discovery, queue, timer, worker or network activity.
- The endpoint defaults to the `ANALYTICS_ENDPOINT` environment variable.
- Transport failures never enter the business path or recursively create Error
  Contract events.
- Queues are bounded and requests use short timeouts.
- Error analytics reuse the existing structured error event instead of counting
  failures twice.
- Error payloads may include code, privacy-safe fingerprint, project-relative
  affected file and line. Retries reuse `event_id`; new occurrences do not.
- Producers validate before enqueueing; collectors repeat validation before storage.
- Tags use a fixed reviewed allowlist and extensions are bounded `x_` fields.
- Source, stack traces, absolute paths, secrets, prompts, personal data and raw
  SQL are excluded by default.

## Stable API 1.0

The fixed protocol lives in:

- [`schemas/event.schema.json`](schemas/event.schema.json) — event envelope
- [`schemas/contract.schema.json`](schemas/contract.schema.json) — project config
- [`schemas/api.openapi.yaml`](schemas/api.openapi.yaml) — ingestion and query API

Projects send batches to `POST /v1/events`. A later adapter uses
`POST /v1/query` to investigate time series and related structured errors. Human
questions are translated by the adapter; they are not baked into the transport.

## CLI

```powershell
analytics-contract detect .
analytics-contract init .
analytics-contract plan .
analytics-contract validate .
```

`init` creates `analytics_contract.json` without overwriting an existing human
configuration unless `--force` is explicitly passed.

## Install

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

See [`INSTALL.md`](INSTALL.md) for Codex, Grok and Claude setup.

## Project Structure

| Path | Purpose |
|---|---|
| `analytics_contract/` | Detection, config, event validation and CLI |
| `schemas/` | Stable public config, event and API schemas |
| `skill-pack/` | Agent rules for automatic planning and instrumentation |
| `scripts/` | Windows and Unix installation |
| `test_analytics_contract.py` | Cross-language and safety regressions |

## Version History

### v1.0.1

- Defined testable zero-work behavior while analytics is disabled or offline.
- Separated delivery idempotency (`event_id`) from error grouping (`fingerprint`).
- Added bounded tag and extension validation at producer and collector boundaries.
- Separated Contract SemVer from event schema and collector API versions.
- Added mandatory acceptance requirements for future language-native adapters.

### v1.0.0

- Added language-neutral project and Error Inbox detection.
- Added disabled-by-default, fail-silent project configuration.
- Added metric planning for Docker, web, rendering, jobs, databases and models.
- Added stable ingestion/query API and privacy-safe error linkage.
- Added Codex, Grok and Claude skills for migration and new-code instrumentation.

## License

**MIT** © 2024–2026 J. Apps — full text: repository root
[`LICENSE`](../../LICENSE). No duplicate license copy is kept here.

## Support & Contact

- **Email:** contact@jappshome.de
- **Website:** [jappshome.de](https://jappshome.de)
- **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)

