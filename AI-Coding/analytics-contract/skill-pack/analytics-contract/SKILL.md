---
name: analytics-contract
description: >
  Language-neutral analytics and telemetry contract built on Error Contract.
  Use whenever building or changing runtime code, metrics, monitoring, logs,
  performance, Docker resources, API timings, FPS, jobs, or error reporting.
  Analytics is opt-in, fail-silent, privacy-safe, and backend-optional.
metadata:
  short-description: "Opt-in analytics foundation for every project"
---

# Analytics Contract

Analytics Contract defines the shared event language for all projects. It adds
useful instrumentation without making an analytics backend a runtime dependency.

## Before runtime code changes

1. Run `analytics-contract detect PROJECT`.
2. Read the root `analytics_contract.json`; if missing, run
   `analytics-contract init PROJECT`.
3. Keep `analytics.enabled=false` unless the human explicitly enables it.
4. Run `analytics-contract plan PROJECT` and select only metrics relevant to the
   code being created or changed.

## Hard runtime guarantees

- The project must start and work when analytics is disabled, unconfigured, or unreachable.
- Disabled means no transport discovery, queues, timers, worker threads, or network calls.
- Transport is fail-silent, short-timeout, bounded, asynchronous where appropriate,
  and must never recurse into the Error Contract inbox.
- Validate the privacy-safe envelope before enqueueing or transport. A collector
  must repeat the same validation and reject unsafe payloads.
- Do not instrument every function. Instrument user actions, API boundaries,
  jobs, external calls, pipelines, render loops, and other meaningful operations.
- Reuse one Error Contract failure event. Never count the same failure twice.
- Keep delivery identity and failure grouping separate: retries reuse `event_id`;
  repeated occurrences receive new event IDs but may share `error.fingerprint`.
- Error analytics may include the structured code and project-relative affected
  file plus optional line. Never include source, stack traces, absolute paths,
  secrets, prompts, raw SQL, or personal data by default.
- Endpoint and token come from runtime configuration or environment variables;
  never commit a real IP or token.

## While building or migrating

- New or substantially changed operations receive relevant analytics immediately.
- Existing projects receive a migration plan; there is no debt baseline that
  silently declares missing instrumentation acceptable.
- Follow the project's language and architecture. The event envelope is shared;
  the local adapter implementation is language-native.

For the stable payload and API, read
[`references/protocol.md`](references/protocol.md). For metric selection, read
[`references/metrics.md`](references/metrics.md). Every adapter must pass
[`references/adapters.md`](references/adapters.md).

